"""Thin-only ACP local bridge with persistent listen support."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ACP_ROOT = Path(__file__).resolve().parent
if str(ACP_ROOT) not in sys.path:
    sys.path.insert(0, str(ACP_ROOT))

import websockets
from runner_support import (
    build_reply_payload,
    execute_provider,
    extract_task_spec,
    load_runner_entry,
    normalize_workspace_path,
    runner_state_key,
    save_runner_entry,
    utc_now_iso as runner_utc_now_iso,
)

from acp_distribution import AgentDistribution, load_distribution

DEFAULT_BACKOFF = (0.5, 1.0, 2.0, 5.0)
DEFAULT_POLL_MS = 800
DEFAULT_LISTEN_TIMEOUT_SECONDS = 300.0
TRANSIENT_HTTP_STATUS_CODES = {502, 503, 504}
TRANSIENT_RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
TRANSIENT_RETRY_SAFE_POST_ROUTES = {
    "/sessions/wait",
    "/sessions/status",
    "/sessions/heartbeat",
    "/sessions/cancel-wait",
    "/sessions/leave",
}
VALID_ACTIONS = ("TASK", "REPLY", "INFO")
_LONG_TASK_MARKER = re.compile(r"^\s*\[(?:busy-hold|busy|long)(?::(?P<minutes>\d+(?:\.\d+)?))?\]\s*", re.IGNORECASE)
_DISTRIBUTION = load_distribution(ACP_ROOT)
TURN_BASED_LISTEN_COMMAND = (
    "python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json "
    "--stop-after-message --timeout-seconds 300"
)
PERSISTENT_LISTEN_WARNING = (
    "WARNING: persistent listen blocks the current process. If this is a turn-based LLM agent that also executes "
    f"work, do NOT use persistent listen or managed-join as the receiver. Use: {TURN_BASED_LISTEN_COMMAND}"
)


@dataclass(frozen=True)
class RuntimeSettings:
    agent_name: str
    hub_ws: str
    token: str | None
    inbox_dir: Path
    outbox_dir: Path
    sent_dir: Path
    poll_ms: int
    backoff: tuple[float, ...]
    connect_timeout: float


@dataclass(frozen=True)
class SendSettings:
    outbox_dir: Path


@dataclass(frozen=True)
class HubAgentSettings:
    config_path: Path
    config: dict[str, Any]
    base_dir: Path
    agent_name: str
    hub_http: str
    hub_ws: str | None
    token: str | None
    session_id: str | None
    member_token: str | None
    dashboard_session_path: str


def _distribution() -> AgentDistribution:
    return _DISTRIBUTION


def _default_hub_http() -> str:
    distribution = _distribution()
    if distribution.default_hub_mode == "official" and distribution.default_hub_http:
        return distribution.default_hub_http
    return ""


def _default_hub_ws() -> str | None:
    distribution = _distribution()
    if distribution.default_hub_mode == "official" and distribution.default_hub_ws:
        return distribution.default_hub_ws
    return None


def _default_hub_label() -> str:
    return _distribution().default_hub_label


def _distribution_id() -> str:
    return _distribution().distribution_id


def _normalize_dashboard_session_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    return cleaned


def _hub_mode_for_http(hub_http: str | None) -> str:
    default_hub_http = _default_hub_http()
    if default_hub_http and isinstance(hub_http, str) and hub_http.rstrip("/") == default_hub_http:
        return "official"
    return "custom"


class LiveSocketAdapter:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def send_text(self, payload: str) -> None:
        await self.websocket.send(payload)

    async def receive_text(self) -> str:
        frame = await self.websocket.recv()
        if isinstance(frame, bytes):
            return frame.decode("utf-8")
        if isinstance(frame, str):
            return frame
        raise TypeError("websocket frame must be text or UTF-8 bytes")

    async def close(self, *, code: int = 1000, reason: str = "acp-shutdown") -> None:
        await self.websocket.close(code=code, reason=reason)


class ACPClientRuntime:
    def __init__(
        self,
        *,
        agent_name: str,
        hub_ws: str,
        inbox_dir: Path,
        outbox_dir: Path,
        sent_dir: Path,
        token: str | None = None,
        poll_ms: int = DEFAULT_POLL_MS,
        backoff: tuple[float, ...] = DEFAULT_BACKOFF,
        connect_timeout: float = 10.0,
    ) -> None:
        self.agent_name = agent_name
        self.hub_ws = hub_ws
        self.inbox_dir = Path(inbox_dir)
        self.outbox_dir = Path(outbox_dir)
        self.sent_dir = Path(sent_dir)
        self.token = token
        self.poll_ms = poll_ms
        self.backoff = backoff
        self.connect_timeout = connect_timeout
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        ensure_queue_dirs(self.inbox_dir, self.outbox_dir, self.sent_dir)
        attempt = 0
        while not self._stop_event.is_set():
            websocket = await self._connect_or_backoff(attempt)
            if websocket is None:
                attempt = min(attempt + 1, len(self.backoff) - 1)
                continue

            try:
                await register_hello(websocket, name=self.agent_name, token=self.token)
                # Only reset backoff once the session is genuinely productive.
                # Resetting on TCP connect alone makes a connect-then-HELLO-fail
                # loop (e.g. bad token) reconnect with no backoff escalation.
                attempt = 0
                await self._run_live_loops(websocket)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                await safe_close(websocket)

            if self._stop_event.is_set():
                break

            await asyncio.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
            attempt = min(attempt + 1, len(self.backoff) - 1)

    async def _connect_or_backoff(self, attempt: int) -> LiveSocketAdapter | None:
        try:
            websocket = await websockets.connect(self.hub_ws, open_timeout=self.connect_timeout)
            return LiveSocketAdapter(websocket)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
            return None

    async def _run_live_loops(self, websocket: LiveSocketAdapter) -> None:
        reader_task = asyncio.create_task(self._reader_loop(websocket))
        sender_task = asyncio.create_task(self._sender_loop(websocket))
        done, pending = await asyncio.wait({reader_task, sender_task}, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            try:
                error = task.exception()
            except asyncio.CancelledError:
                continue
            if error is not None:
                raise error

        raise ConnectionError("acp client loop ended unexpectedly")

    async def _reader_loop(self, websocket: LiveSocketAdapter) -> None:
        while not self._stop_event.is_set():
            frame = await receive_json_frame(websocket)
            if frame.get("type") != "MSG":
                continue
            append_inbound_message(self.inbox_dir, frame)

    async def _sender_loop(self, websocket: LiveSocketAdapter) -> None:
        while not self._stop_event.is_set():
            for path in list_outbound_messages(self.outbox_dir):
                record = load_json_object(path)
                envelope = build_outbound_envelope(agent_name=self.agent_name, record=record)
                await send_json_frame(websocket, envelope)
                archive_sent_message(path, self.sent_dir)
            await asyncio.sleep(max(self.poll_ms, 1) / 1000.0)


def _bundle_version_string() -> str:
    version_file = ACP_ROOT / "VERSION"
    if version_file.exists():
        try:
            return version_file.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            return "unknown"
    return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACP local bridge")
    parser.add_argument(
        "--version",
        action="version",
        version=f"acp {_bundle_version_string()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize ACP_AGENT in a more human-friendly way")
    init_parser.add_argument("--hub-mode", choices=("official", "custom"), default=None, help="Hub mode for bootstrap")
    init_parser.add_argument("--hub-http", default=None, help="Hub HTTP base URL")
    init_parser.add_argument("--hub-ws", default=None, help="Hub websocket URL")
    init_parser.add_argument("--agent", action="append", default=None, help="Agent name to provision. Repeat for multiple agents.")
    init_parser.add_argument("--token", default=None, help="Optional ACP token")
    init_parser.add_argument("--skill-home", default=None, help="Override Codex skill home. Defaults to ~/.codex/skills")
    init_parser.add_argument("--skip-install-deps", action="store_true", help="Skip ACP runtime dependency installation")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing ACP bundle and skill if needed")
    init_parser.add_argument("--non-interactive", "--yes", dest="non_interactive", action="store_true", help="Never prompt during init; fail when required values are missing.")

    run_parser = subparsers.add_parser("run", help="Keep a websocket client alive for one agent")
    run_parser.add_argument("--config", default=None, help="Optional JSON config path")
    run_parser.add_argument("--hub", default=None, help="Hub websocket URL, e.g. ws://localhost:8000/ws")
    run_parser.add_argument("--name", default=None, help="Unique agent name")
    run_parser.add_argument("--token", default=None, help="Optional ACP token")
    run_parser.add_argument("--inbox-dir", default=None, help="Directory for inbound message JSON files")
    run_parser.add_argument("--outbox-dir", default=None, help="Directory for outbound message JSON files")
    run_parser.add_argument("--sent-dir", default=None, help="Directory for sent message archives")
    run_parser.add_argument("--poll-ms", type=int, default=None, help="Outbox poll interval in milliseconds")
    run_parser.add_argument("--backoff", default=None, help="Reconnect backoff delays, comma-separated")
    run_parser.add_argument("--connect-timeout", type=float, default=None, help="Websocket open timeout in seconds")

    send_parser = subparsers.add_parser("send", help="Queue a local outbound message")
    send_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    send_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    send_parser.add_argument("--to", required=True, help="Destination agent name")
    send_parser.add_argument("--action", required=True, choices=VALID_ACTIONS, help="ACP action")
    send_parser.add_argument("--payload", default=None, help="Message payload text (or use --payload-file for shell-safe input)")
    send_parser.add_argument(
        "--payload-file",
        default=None,
        help="Read payload from a file path, or '-' for stdin. Avoids shell quoting issues (e.g. JSON on PowerShell).",
    )
    send_parser.add_argument("--task-id", default=None, help="Optional structured task id to embed into TASK/REPLY payloads")
    send_parser.add_argument("--thread-id", default=None, help="Optional thread UUID")
    send_parser.add_argument("--in-reply-to", "--reply-to", dest="in_reply_to", default=None, help="Optional reply-to message UUID")
    send_parser.add_argument("--outbox-dir", default=None, help="Override outbox directory")

    task_parser = subparsers.add_parser("task", help="Send a TASK using the active or selected agent config")
    task_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    task_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    task_parser.add_argument("--to", required=True, help="Destination agent name")
    task_parser.add_argument("--payload", default=None, help="Task payload text")
    task_parser.add_argument(
        "--payload-file",
        default=None,
        help="Read task payload from a file path, or '-' for stdin (shell-safe for JSON).",
    )
    task_parser.add_argument("text", nargs="*", help="Optional positional task text")
    task_parser.add_argument("--task-id", default=None, help="Optional structured task id to include in the TASK payload")
    task_parser.add_argument("--thread-id", default=None, help="Optional thread UUID")
    task_parser.add_argument("--in-reply-to", "--reply-to", dest="in_reply_to", default=None, help="Optional reply-to message UUID")

    reply_parser = subparsers.add_parser("reply", help="Send a REPLY using the active or selected agent config")
    reply_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    reply_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    reply_parser.add_argument("--to", required=True, help="Destination agent name")
    reply_parser.add_argument("--payload", default=None, help="Reply payload text")
    reply_parser.add_argument(
        "--payload-file",
        default=None,
        help="Read reply payload from a file path, or '-' for stdin (shell-safe for JSON).",
    )
    reply_parser.add_argument("text", nargs="*", help="Optional positional reply text")
    reply_parser.add_argument("--task-id", default=None, help="Optional structured task id to include in the REPLY payload")
    reply_parser.add_argument("--thread-id", default=None, help="Optional thread UUID")
    reply_parser.add_argument("--in-reply-to", "--reply-to", dest="in_reply_to", default=None, help="Optional reply-to message UUID")

    create_parser = subparsers.add_parser("create-session", help="Create a coordination session and persist it into config")
    create_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    create_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    create_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    create_parser.add_argument("--token", default=None, help="Optional ACP token")
    create_parser.add_argument("--title", default=None, help="Optional session title")
    create_parser.add_argument("--project", default=None, help="Optional project label")
    create_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    create_parser.add_argument("--listen", action="store_true", help="Start persistent listen immediately after creating the session")

    join_parser = subparsers.add_parser("join-session", help="Join a coordination session using a join code")
    join_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    join_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    join_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    join_parser.add_argument("--token", default=None, help="Optional ACP token")
    join_parser.add_argument("--code", required=True, help="Join code from the chief agent")
    join_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    join_parser.add_argument("--listen", action="store_true", help="Start persistent listen immediately after joining the session")

    start_parser = subparsers.add_parser("start", help="Create a session and immediately enter listen mode")
    start_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    start_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    start_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    start_parser.add_argument("--token", default=None, help="Optional ACP token")
    start_parser.add_argument("--title", default=None, help="Optional session title")
    start_parser.add_argument("--project", default=None, help="Optional project label")
    start_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    start_parser.add_argument("--no-listen", action="store_true", help="Create the session but do not start listen immediately")

    quick_join_parser = subparsers.add_parser("join", help="Join a session and immediately enter listen mode")
    quick_join_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    quick_join_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    quick_join_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    quick_join_parser.add_argument("--token", default=None, help="Optional ACP token")
    quick_join_parser.add_argument("code", help="Join code from the chief agent")
    quick_join_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    quick_join_parser.add_argument("--no-listen", action="store_true", help="Join the session but do not start listen immediately")

    managed_start_parser = subparsers.add_parser("managed-start", help="Create a session through a managed workspace token and enter listen mode")
    managed_start_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    managed_start_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    managed_start_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    managed_start_parser.add_argument("--hub-ws", default=None, help="Override managed Hub websocket URL used after binding")
    managed_start_parser.add_argument("--workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    managed_start_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    managed_start_parser.add_argument("--title", default=None, help="Optional session title")
    managed_start_parser.add_argument("--project", default=None, help="Optional project label")
    managed_start_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    managed_start_parser.add_argument("--no-listen", action="store_true", help="Create the session but do not start listen immediately")

    managed_join_parser = subparsers.add_parser(
        "managed-join",
        help="Join a workspace session through a managed workspace token, persist config, and exit by default",
    )
    managed_join_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    managed_join_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    managed_join_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    managed_join_parser.add_argument("--hub-ws", default=None, help="Override managed Hub websocket URL used after binding")
    managed_join_parser.add_argument("--workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    managed_join_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    managed_join_parser.add_argument("--session-id", required=True, help="Workspace session id to join")
    managed_join_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this member")
    managed_join_parser.add_argument("--no-listen", action="store_true", help="Deprecated no-op: managed-join already exits after attach by default")
    managed_join_parser.add_argument(
        "--listen-once",
        action="store_true",
        help="After joining, receive one message with listen --stop-after-message and exit (recommended for turn-based agents)",
    )
    managed_join_parser.add_argument(
        "--listen-persistent",
        action="store_true",
        help="After joining, start persistent listen. WARNING: use only for daemons/listeners, not turn-based LLM executors.",
    )

    managed_sessions_parser = subparsers.add_parser("managed-sessions", help="List workspace sessions through a managed workspace token")
    managed_sessions_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    managed_sessions_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    managed_sessions_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    managed_sessions_parser.add_argument("--workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    managed_sessions_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")

    managed_close_parser = subparsers.add_parser("managed-close", help="Close and remove a managed workspace session through a managed workspace token")
    managed_close_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    managed_close_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    managed_close_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    managed_close_parser.add_argument("--workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    managed_close_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    managed_close_parser.add_argument("--session-id", required=True, help="Workspace session id to close")
    managed_close_parser.add_argument("--detail", default=None, help="Optional close reason")

    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Find a managed workspace session for this project, join it, announce readiness, and prepare runner mode",
    )
    onboard_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    onboard_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem to onboard. If omitted, ACP auto-resolves a single config or reads --config.")
    onboard_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    onboard_parser.add_argument("--hub-ws", default=None, help="Override managed Hub websocket URL used after binding")
    onboard_parser.add_argument("--workspace", default=None, help="Local project workspace path for runner mode and project detection")
    onboard_parser.add_argument("--managed-workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    onboard_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    onboard_parser.add_argument("--session-id", default=None, help="Join this exact managed session id instead of matching by project")
    onboard_parser.add_argument("--project", default=None, help="Project label used to match an active managed session. Defaults to .acp/project-id, git root name, or workspace folder name.")
    onboard_parser.add_argument("--role", default="worker", choices=("worker", "chief"), help="Onboarding role. Worker is implemented first; chief is reserved for the autonomous-chief flow.")
    onboard_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise, e.g. backend,python")
    onboard_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Local provider to prepare for runner mode")
    onboard_parser.add_argument("--wait-for-session", type=float, default=120.0, help="Seconds to poll managed sessions until a matching project session appears")
    onboard_parser.add_argument("--prefer-latest", action="store_true", help="If several matching sessions exist, pick the latest by created_at instead of failing")
    onboard_parser.add_argument("--to", default=None, help="Chief/member to notify after joining. Defaults to the managed session owner.")
    onboard_parser.add_argument("--skip-ready", action="store_true", help="Join and prepare runner mode without sending the readiness INFO message")
    onboard_parser.add_argument("--start-runner", action="store_true", help="After onboarding, enter runner start and keep the process alive")
    onboard_parser.add_argument("--wait-timeout-seconds", type=float, default=120.0, help="Runner per-request wait timeout (max 300)")
    onboard_parser.add_argument("--task-timeout-seconds", type=float, default=1800.0, help="Runner provider execution timeout")
    onboard_parser.add_argument("--retry-delay-seconds", type=float, default=2.0, help="Runner delay before retrying transient errors")

    connect_parser = subparsers.add_parser(
        "connect",
        help="Self-describing managed entrypoint: join as worker or orient/start the chief flow",
    )
    connect_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    connect_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem to connect")
    connect_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    connect_parser.add_argument("--hub-ws", default=None, help="Override managed Hub websocket URL used after binding")
    connect_parser.add_argument("--workspace", default=None, help="Local project workspace path for runner/chief mode and project detection")
    connect_parser.add_argument("--managed-workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    connect_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    connect_parser.add_argument("--session-id", default=None, help="Join this exact managed session id instead of matching by project")
    connect_parser.add_argument("--project", default=None, help="Project label used to match an active managed session")
    connect_parser.add_argument("--role", default="auto", choices=("auto", "worker", "chief"), help="Connect as worker, chief, or infer from existing config")
    connect_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise")
    connect_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Local provider for worker runner mode")
    connect_parser.add_argument("--wait-for-session", type=float, default=120.0, help="Seconds to poll managed sessions until a matching project session appears")
    connect_parser.add_argument("--prefer-latest", action="store_true", help="If several matching sessions exist, pick the latest by created_at instead of failing")
    connect_parser.add_argument("--skip-ready", action="store_true", help="Join and prepare runner mode without sending the readiness INFO message")
    connect_parser.add_argument("--start-runner", action="store_true", help="After worker onboarding, enter runner start and keep the process alive")
    connect_parser.add_argument("--start-chief", action="store_true", help="If connected as chief, enter chief start and keep the process alive")
    connect_parser.add_argument("--backlog-dir", default=None, help="Chief backlog directory. Defaults to coord/backlog")
    connect_parser.add_argument("--wait-timeout-seconds", type=float, default=120.0, help="Runner/chief per-request wait timeout")
    connect_parser.add_argument("--task-timeout-seconds", type=float, default=1800.0, help="Runner provider execution timeout")
    connect_parser.add_argument("--retry-delay-seconds", type=float, default=2.0, help="Runner delay before retrying transient errors")

    coordinate_parser = subparsers.add_parser(
        "coordinate",
        help="Connect through managed ACP and wait for one turn-ready message",
    )
    coordinate_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    coordinate_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem to coordinate")
    coordinate_parser.add_argument("--hub-http", default=None, help="Override managed Hub HTTP base URL")
    coordinate_parser.add_argument("--hub-ws", default=None, help="Override managed Hub websocket URL used after binding")
    coordinate_parser.add_argument("--workspace", default=None, help="Local project workspace path for project detection")
    coordinate_parser.add_argument("--managed-workspace", default=None, help="Optional managed workspace slug. Current ACP managed hubs can infer it from the token.")
    coordinate_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Defaults to managed_agent_token in the selected config.")
    coordinate_parser.add_argument("--session-id", default=None, help="Join this exact managed session id instead of matching by project")
    coordinate_parser.add_argument("--project", default=None, help="Project label used to match an active managed session")
    coordinate_parser.add_argument("--role", default="worker", choices=("auto", "worker", "chief"), help="Coordinate as worker, chief, or infer from existing config")
    coordinate_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise")
    coordinate_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Local provider to persist for runner mode")
    coordinate_parser.add_argument("--wait-for-session", type=float, default=120.0, help="Seconds to poll managed sessions until a matching project session appears")
    coordinate_parser.add_argument("--prefer-latest", action="store_true", help="If several matching sessions exist, pick the latest by created_at instead of failing")
    coordinate_parser.add_argument("--skip-ready", action="store_true", help="Join and prepare runner mode without sending the readiness INFO message")
    coordinate_parser.add_argument("--listen-timeout-seconds", type=float, default=DEFAULT_LISTEN_TIMEOUT_SECONDS, help="Seconds to wait for one incoming coordination message")
    coordinate_parser.add_argument("--retry-delay-seconds", type=float, default=2.0, help="Delay before retrying transient wait errors")

    invite_parser = subparsers.add_parser("invite", help="Generate a role-aware ACP invitation prompt")
    invite_parser.add_argument("--config", default=None, help="JSON config path for the inviting/local agent")
    invite_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Default invitee agent name")
    invite_parser.add_argument("--role", default="worker", choices=("worker", "chief"), help="Role to invite")
    invite_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags for the invitee")
    invite_parser.add_argument("--project", default=None, help="Project label for connect/onboard")
    invite_parser.add_argument("--workspace", default=None, help="Workspace path placeholder or value")
    invite_parser.add_argument("--session-id", default=None, help="Managed session id to join")
    invite_parser.add_argument("--hub-http", default=None, help="Hub HTTP base URL to mention")

    onboard_help_parser = subparsers.add_parser(
        "onboard-help",
        help="Print a self-contained ACP quickstart that does not require the skill to be installed globally",
    )
    onboard_help_parser.add_argument("--hub-http", default=None, help="Hub HTTP base URL to mention")
    onboard_help_parser.add_argument("--project", default=None, help="Project label to mention")
    onboard_help_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name placeholder")

    attach_session_parser = subparsers.add_parser("attach-session", help="Persist an existing session binding and enter listen mode")
    attach_session_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    attach_session_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    attach_session_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    attach_session_parser.add_argument("--hub-ws", default=None, help="Override Hub websocket URL used after binding")
    attach_session_parser.add_argument("--session-id", required=True, help="Existing ACP session id")
    attach_session_parser.add_argument("--member-token", required=True, help="Existing ACP member token for this agent")
    attach_session_parser.add_argument("--join-code", default=None, help="Optional join code to persist for convenience")
    attach_session_parser.add_argument("--member-role", default=None, help="Optional member role to persist")
    attach_session_parser.add_argument("--no-listen", action="store_true", help="Persist the binding but do not start listen immediately")

    quickstart_parser = subparsers.add_parser(
        "quickstart",
        help="One command: install skill+deps, provision a local-mode agent config, and start a local Hub",
    )
    quickstart_parser.add_argument(
        "--agent", "--name", dest="agent", action="append", required=True,
        help="Agent name to provision. Repeat for multiple agents.",
    )
    quickstart_parser.add_argument("--host", default=LOCAL_HUB_DEFAULT_HOST, help="Local hub bind host")
    quickstart_parser.add_argument("--port", type=int, default=LOCAL_HUB_DEFAULT_PORT, help="Local hub port")
    quickstart_parser.add_argument("--token", default=None, help="Optional ACP token to store in the config")
    quickstart_parser.add_argument("--skill-home", default=None, help="Override Codex skill home")
    quickstart_parser.add_argument("--claude-skill-home", default=None, help="Override Claude skill home")
    quickstart_parser.add_argument("--skip-install-deps", action="store_true", help="Skip the pip dependency install step")

    hub_up_parser = subparsers.add_parser(
        "hub-up",
        help="Start (or reuse) a local Hub on 127.0.0.1 for zero-infra coordination",
    )
    hub_up_parser.add_argument("--host", default=LOCAL_HUB_DEFAULT_HOST, help="Local hub bind host")
    hub_up_parser.add_argument("--port", type=int, default=LOCAL_HUB_DEFAULT_PORT, help="Local hub port")
    hub_up_parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=15.0,
        help="Seconds to wait for the local hub to become healthy",
    )

    subparsers.add_parser("hub-down", help="Stop the local Hub started by hub-up")
    subparsers.add_parser("hub-status", help="Show local Hub status")

    wait_parser = subparsers.add_parser(
        "wait",
        help="Run one foreground wait cycle until a session message arrives or the request times out",
    )
    wait_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    wait_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    wait_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="One-shot long-poll timeout in seconds (Hub max 300 per request)",
    )

    cancel_wait_parser = subparsers.add_parser("cancel-wait", help="Cancel this member's active wait/listen request on the Hub")
    cancel_wait_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    cancel_wait_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")

    wait_window_parser = subparsers.add_parser(
        "wait-window",
        help="Hold a foreground active-wait window by chaining one-shot waits until a message arrives or the window closes",
    )
    wait_window_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    wait_window_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    wait_window_parser.add_argument(
        "--window-minutes",
        type=float,
        default=20.0,
        help="Foreground active-wait window in minutes",
    )
    wait_window_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="Per-request long-poll timeout in seconds (Hub max 300 per request)",
    )
    wait_window_parser.add_argument(
        "--auto-busy-heartbeat-minutes",
        type=float,
        default=0.0,
        help="If > 0, TASK payloads marked [long] will start a background busy heartbeat hold for this many minutes",
    )
    wait_window_parser.add_argument(
        "--auto-busy-heartbeat-interval-seconds",
        type=float,
        default=45.0,
        help="Heartbeat interval used by auto busy hold after a marked TASK arrives",
    )

    listen_parser = subparsers.add_parser("listen", help="Listen for session messages")
    listen_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    listen_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    listen_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_LISTEN_TIMEOUT_SECONDS,
        help="Per-request long-poll timeout in seconds (max 300 on the Hub)",
    )
    listen_parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=2.0,
        help="Delay before retrying after transient listener errors",
    )
    listen_parser.add_argument(
        "--stop-after-message",
        action="store_true",
        help="Exit after the first received message instead of staying in persistent listen mode",
    )
    listen_parser.add_argument(
        "--auto-busy-heartbeat-minutes",
        type=float,
        default=0.0,
        help="If > 0 and --stop-after-message is used, TASK payloads marked [long] start a background busy heartbeat hold",
    )
    listen_parser.add_argument(
        "--auto-busy-heartbeat-interval-seconds",
        type=float,
        default=45.0,
        help="Heartbeat interval used by auto busy hold after a marked TASK arrives",
    )
    listen_parser.add_argument(
        "--update-policy",
        choices=("off", "notify", "auto-when-idle"),
        default=None,
        help="Check the release channel before listening; auto-when-idle updates only safe untracked installs",
    )
    listen_parser.add_argument("--manifest-url", default=None, help="Override ACP_AGENT release manifest URL")
    listen_parser.add_argument(
        "--allow-tracked-auto-update",
        action="store_true",
        help="Allow auto-when-idle to update even when ACP_AGENT files are tracked by git",
    )

    status_parser = subparsers.add_parser("status", help="Update this agent status inside the session")
    status_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    status_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    status_parser.add_argument("--state", required=True, choices=("idle", "waiting", "busy"), help="Agent state")
    status_parser.add_argument("--text", default=None, help="Optional human-readable state detail")
    status_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to publish/update for this member")
    status_parser.add_argument(
        "--heartbeat-window-minutes",
        type=float,
        default=0.0,
        help="If > 0, keep this status alive by sending heartbeats during the given window",
    )
    status_parser.add_argument(
        "--heartbeat-interval-seconds",
        type=float,
        default=45.0,
        help="Heartbeat interval used with --heartbeat-window-minutes",
    )

    heartbeat_parser = subparsers.add_parser("heartbeat", help="Touch this session member as alive without changing status")
    heartbeat_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    heartbeat_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    heartbeat_parser.add_argument("--text", default=None, help="Optional visible heartbeat detail for the session dashboard")
    heartbeat_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to publish/update for this member")

    leave_parser = subparsers.add_parser("leave-session", help="Leave the current session and clear local session credentials")
    leave_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    leave_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")

    info_parser = subparsers.add_parser("session-info", help="Fetch the current session snapshot for this agent")
    info_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    info_parser.add_argument("--agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    info_parser.add_argument("--manifest-url", default=None, help="Override ACP_AGENT release manifest URL for update hints")
    info_parser.add_argument("--skip-update-check", action="store_true", help="Do not include release-channel update hints")

    update_check_parser = subparsers.add_parser("update-check", help="Check the ACP_AGENT release channel")
    update_check_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http from")
    update_check_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    update_check_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    update_check_parser.add_argument("--manifest-url", default=None, help="Override ACP_AGENT release manifest URL")

    self_update_parser = subparsers.add_parser("self-update", help="Update ACP_AGENT from the release channel")
    self_update_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http from")
    self_update_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    self_update_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    self_update_parser.add_argument("--manifest-url", default=None, help="Override ACP_AGENT release manifest URL")
    self_update_parser.add_argument("--force", action="store_true", help="Apply even when local and remote versions match")
    self_update_parser.add_argument("--auto-when-idle", action="store_true", help="Use autonomous safety guard before updating")
    self_update_parser.add_argument("--allow-tracked-repo", action="store_true", help="Allow update even when ACP_AGENT files are tracked by git")

    # Hub inspection commands (Phase 12: HCTX-01/02/03 — wrapper coverage).
    health_parser = subparsers.add_parser("health", help="GET /health on the hub")
    health_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http from")
    health_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    health_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    health_parser.add_argument("--token", default=None, help="Optional ACP token")

    agents_parser = subparsers.add_parser("agents", help="GET /agents (live agents connected to the hub)")
    agents_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http from")
    agents_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    agents_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    agents_parser.add_argument("--token", default=None, help="Optional ACP token (required if hub enforces it)")

    overview_parser = subparsers.add_parser("overview", help="GET /dashboard/overview (admin token required)")
    overview_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http and token from")
    overview_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    overview_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    overview_parser.add_argument("--token", default=None, help="Admin token. Falls back to config.token if not set.")

    sessions_parser = subparsers.add_parser("sessions", help="List sessions via /dashboard/overview (admin token required)")
    sessions_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http and token from")
    sessions_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    sessions_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    sessions_parser.add_argument("--token", default=None, help="Admin token. Falls back to config.token if not set.")
    sessions_parser.add_argument("--active", action="store_true", help="Only return sessions in active state")

    replay_parser = subparsers.add_parser("replay", help="GET replay events. Uses admin replay when --token/config.token is present, or managed session replay with managed_agent_token.")
    replay_parser.add_argument("--config", default=None, help="JSON config path to resolve hub_http and token from")
    replay_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    replay_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    replay_parser.add_argument("--token", default=None, help="Admin token. Falls back to config.token if not set.")
    replay_parser.add_argument("--agent-token", default=None, help="Managed workspace agent token. Falls back to config.managed_agent_token.")
    replay_parser.add_argument("--session-id", default=None, help="Managed session id. Falls back to config.session_id.")
    replay_parser.add_argument("--from-ts", dest="from_ts", default=None, help="Lower bound timestamp (RFC3339)")
    replay_parser.add_argument("--to-ts", dest="to_ts", default=None, help="Upper bound timestamp (RFC3339)")
    replay_parser.add_argument("--actor", default=None, help="Filter by actor")
    replay_parser.add_argument("--action", default=None, choices=("TASK", "REPLY", "INFO"), help="Managed replay filter by session action")
    replay_parser.add_argument("--event-type", dest="event_type", default=None,
                               help="received | routed | rejected | delivery_failed")
    replay_parser.add_argument("--message-id", dest="message_id", default=None, help="Filter by message UUID")
    replay_parser.add_argument("--thread-id", dest="thread_id", default=None, help="Filter by thread UUID")
    replay_parser.add_argument("--order", default=None, choices=("asc", "desc"), help="Result order")
    replay_parser.add_argument("--limit", default=None, help="Max events to return (capped server-side)")
    replay_parser.add_argument("--cursor", default=None, help="Opaque pagination cursor from previous call")

    doctor_parser = subparsers.add_parser("doctor", help="End-to-end diagnostics for this ACP_AGENT install")
    doctor_parser.add_argument("--config", default=None, help="Optional JSON config path to verify")
    doctor_parser.add_argument("--agent", default=None, help="Agent stem. If omitted, ACP auto-resolves a single config.")
    doctor_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    doctor_parser.add_argument("--token", default=None, help="Optional admin token")

    runner_parser = subparsers.add_parser("runner", help="Run a headless ACP runner backed by a local provider")
    runner_subparsers = runner_parser.add_subparsers(dest="runner_command", required=True)

    runner_start_parser = runner_subparsers.add_parser("start", help="Stay connected to a session and execute TASK messages")
    runner_start_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    runner_start_parser.add_argument("--join-code", default=None, help="Join code to attach the runner to a session")
    runner_start_parser.add_argument("--agent", "--agent-name", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    runner_start_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    runner_start_parser.add_argument("--hub-ws", default=None, help="Optional Hub websocket URL to persist in generated config")
    runner_start_parser.add_argument("--token", default=None, help="Optional ACP token")
    runner_start_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Local provider to spawn")
    runner_start_parser.add_argument("--workspace", default=None, help="Workspace path for the provider process")
    runner_start_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this runner")
    runner_start_parser.add_argument("--session-id", default=None, help="Restore an existing session id")
    runner_start_parser.add_argument("--member-token", default=None, help="Restore an existing member token")
    runner_start_parser.add_argument("--wait-timeout-seconds", type=float, default=120.0, help="Per-request wait timeout (max 300)")
    runner_start_parser.add_argument("--task-timeout-seconds", type=float, default=1800.0, help="Timeout for provider execution")
    runner_start_parser.add_argument("--retry-delay-seconds", type=float, default=2.0, help="Delay before retrying transient errors")
    runner_start_parser.add_argument("--auto-busy-heartbeat-minutes", type=float, default=None, help="For TASK instructions marked [long]/[busy-hold], keep busy heartbeat alive for this many minutes")
    runner_start_parser.add_argument("--auto-busy-heartbeat-interval-seconds", type=float, default=None, help="Heartbeat interval used by runner auto busy hold")

    runner_once_parser = runner_subparsers.add_parser("once", help="Process at most one incoming TASK and exit")
    runner_once_parser.add_argument("--config", default=None, help="JSON config path for the local agent")
    runner_once_parser.add_argument("--join-code", default=None, help="Join code to attach the runner to a session")
    runner_once_parser.add_argument("--agent", "--agent-name", "--name", dest="agent", default=None, help="Agent name/config stem. If omitted, ACP auto-resolves a single config.")
    runner_once_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    runner_once_parser.add_argument("--hub-ws", default=None, help="Optional Hub websocket URL to persist in generated config")
    runner_once_parser.add_argument("--token", default=None, help="Optional ACP token")
    runner_once_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Local provider to spawn")
    runner_once_parser.add_argument("--workspace", default=None, help="Workspace path for the provider process")
    runner_once_parser.add_argument("--capabilities", default=None, help="Comma-separated capability tags to advertise for this runner")
    runner_once_parser.add_argument("--session-id", default=None, help="Restore an existing session id")
    runner_once_parser.add_argument("--member-token", default=None, help="Restore an existing member token")
    runner_once_parser.add_argument("--wait-timeout-seconds", type=float, default=120.0, help="Per-request wait timeout (max 300)")
    runner_once_parser.add_argument("--task-timeout-seconds", type=float, default=1800.0, help="Timeout for provider execution")
    runner_once_parser.add_argument("--auto-busy-heartbeat-minutes", type=float, default=None, help="For TASK instructions marked [long]/[busy-hold], keep busy heartbeat alive for this many minutes")
    runner_once_parser.add_argument("--auto-busy-heartbeat-interval-seconds", type=float, default=None, help="Heartbeat interval used by runner auto busy hold")

    chief_parser = subparsers.add_parser("chief", help="Run an autonomous ACP chief that dispatches file-backed backlog tasks")
    chief_subparsers = chief_parser.add_subparsers(dest="chief_command", required=True)

    chief_start_parser = chief_subparsers.add_parser("start", help="Keep the chief alive, drain replies, and dispatch backlog tasks")
    chief_start_parser.add_argument("--config", default=None, help="JSON config path for the chief agent")
    chief_start_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Chief agent name/config stem. If omitted, ACP auto-resolves a single config.")
    chief_start_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    chief_start_parser.add_argument("--hub-ws", default=None, help="Optional Hub websocket URL")
    chief_start_parser.add_argument("--token", default=None, help="Optional ACP token")
    chief_start_parser.add_argument("--backlog-dir", default=None, help="File backlog directory. Defaults to coord/backlog relative to config/project.")
    chief_start_parser.add_argument("--workspace", default=None, help="Default workspace path to pass to runner workers")
    chief_start_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Default provider to pass to runner workers")
    chief_start_parser.add_argument("--wait-timeout-seconds", type=float, default=30.0, help="Per-loop wait timeout before a dispatch tick")
    chief_start_parser.add_argument("--tick-seconds", type=float, default=2.0, help="Sleep between dispatch ticks")
    chief_start_parser.add_argument("--assignment-ttl-seconds", type=float, default=None, help="Requeue assigned tasks that have not produced a valid REPLY after this many seconds; <=0 disables")
    chief_start_parser.add_argument("--once", action="store_true", help="Run a single dispatch/reply-drain tick and exit")

    chief_once_parser = chief_subparsers.add_parser("once", help="Run one chief dispatch/reply-drain tick and exit")
    chief_once_parser.add_argument("--config", default=None, help="JSON config path for the chief agent")
    chief_once_parser.add_argument("--agent", "--name", dest="agent", default=None, help="Chief agent name/config stem. If omitted, ACP auto-resolves a single config.")
    chief_once_parser.add_argument("--hub-http", default=None, help="Override Hub HTTP base URL")
    chief_once_parser.add_argument("--hub-ws", default=None, help="Optional Hub websocket URL")
    chief_once_parser.add_argument("--token", default=None, help="Optional ACP token")
    chief_once_parser.add_argument("--backlog-dir", default=None, help="File backlog directory. Defaults to coord/backlog relative to config/project.")
    chief_once_parser.add_argument("--workspace", default=None, help="Default workspace path to pass to runner workers")
    chief_once_parser.add_argument("--provider", default=None, choices=("codex_local", "claude_local"), help="Default provider to pass to runner workers")
    chief_once_parser.add_argument("--wait-timeout-seconds", type=float, default=0.0, help="Optional one-shot wait timeout before dispatch")
    chief_once_parser.add_argument("--assignment-ttl-seconds", type=float, default=None, help="Requeue assigned tasks that have not produced a valid REPLY after this many seconds; <=0 disables")
    chief_once_parser.add_argument("--tick-seconds", type=float, default=0.0, help=argparse.SUPPRESS)
    return parser


def load_config(path_value: str | None) -> tuple[dict[str, Any], Path | None]:
    if path_value is None:
        return {}, None
    path = resolve_config_file(path_value)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("config file must contain a top-level JSON object")
    return parsed, path.parent


def resolve_config_file(path_value: str | None) -> Path:
    if path_value is None:
        raise ValueError("config path is required")
    return Path(path_value).expanduser().resolve()


def _default_agents_dir() -> Path:
    return (ACP_ROOT / "agents").resolve()


def list_agent_config_files() -> list[Path]:
    agents_dir = _default_agents_dir()
    if not agents_dir.exists():
        return []
    return sorted(path for path in agents_dir.iterdir() if path.is_file() and path.suffix.lower() == ".json")


def resolve_cli_config_path(
    *,
    config_path: str | None,
    agent_name: str | None = None,
    command_name: str,
    allow_missing_agent_config: bool = False,
) -> Path:
    if isinstance(config_path, str) and config_path.strip():
        return resolve_config_file(config_path)

    normalized_agent = agent_name.strip() if isinstance(agent_name, str) and agent_name.strip() else None
    if normalized_agent is not None:
        candidate = _default_agents_dir() / f"{normalized_agent}.json"
        if candidate.is_file() or allow_missing_agent_config:
            return candidate.resolve()
        raise ValueError(
            f"{command_name} could not find ACP_AGENT/agents/{normalized_agent}.json. "
            "Run 'python ACP_AGENT/acp.py init --agent <name>' first or pass --config explicitly."
        )

    config_files = list_agent_config_files()
    if len(config_files) == 1:
        return config_files[0].resolve()
    if not config_files:
        raise ValueError(
            f"{command_name} needs an agent config, but ACP_AGENT/agents is empty. "
            "Run 'python ACP_AGENT/acp.py init --agent <name>' first."
        )
    available = ", ".join(path.stem for path in config_files)
    raise ValueError(
        f"{command_name} found multiple agent configs. Pass --agent <name> or --config <path>. "
        f"Available: {available}"
    )


def get_config_value(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config:
            return config[key]
    return None


def normalize_capabilities(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raise ValueError("capabilities must be a comma-separated string or array")
    seen: set[str] = set()
    capabilities: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            raise ValueError("capability entries must be strings")
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,63}", cleaned):
            raise ValueError("capability entries may contain lowercase letters, numbers, _, ., :, or -")
        if cleaned not in seen:
            seen.add(cleaned)
            capabilities.append(cleaned)
    return capabilities


def capabilities_from_args_config(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    explicit = getattr(args, "capabilities", None)
    if explicit is not None:
        return normalize_capabilities(explicit)
    return normalize_capabilities(get_config_value(config, "capabilities"))


def optional_capabilities_from_args_config(args: argparse.Namespace, config: dict[str, Any]) -> list[str] | None:
    explicit = getattr(args, "capabilities", None)
    if explicit is not None:
        return normalize_capabilities(explicit)
    if "capabilities" in config:
        return normalize_capabilities(config.get("capabilities"))
    return None


def resolve_config_path(base_dir: Path | None, raw_value: str | None) -> Path | None:
    if raw_value is None:
        return None
    path = Path(raw_value).expanduser()
    if path.is_absolute() or base_dir is None:
        return path.resolve()
    return (base_dir / path).resolve()


def parse_backoff_value(raw_value: object) -> tuple[float, ...]:
    if raw_value is None:
        return DEFAULT_BACKOFF
    if isinstance(raw_value, str):
        parts = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple)):
        parts = [str(item).strip() for item in raw_value if str(item).strip()]
    else:
        raise ValueError("backoff must be a comma-separated string or array")

    if not parts:
        raise ValueError("backoff list must not be empty")
    delays = tuple(float(item) for item in parts)
    if any(delay <= 0 for delay in delays):
        raise ValueError("backoff values must be > 0")
    return delays


def _normalize_hub_http(raw_value: object) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip().rstrip("/")
    return _default_hub_http()


def _resolve_hub_ws(raw_ws: object, *, hub_http: str) -> str | None:
    if isinstance(raw_ws, str) and raw_ws.strip():
        return raw_ws.strip()
    default_hub_http = _default_hub_http()
    if default_hub_http and hub_http == default_hub_http:
        return _default_hub_ws()
    return None


def _derive_hub_ws_from_http(hub_http: str | None) -> str | None:
    if not isinstance(hub_http, str) or not hub_http.strip():
        return None
    parsed = urllib.parse.urlparse(hub_http.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    if parsed.scheme == "https":
        ws_scheme = "wss"
    elif parsed.scheme == "http":
        ws_scheme = "ws"
    else:
        return None
    base_path = parsed.path.rstrip("/")
    ws_path = f"{base_path}/ws" if base_path else "/ws"
    return urllib.parse.urlunparse((ws_scheme, parsed.netloc, ws_path, "", "", ""))


def resolve_runtime_settings(args: argparse.Namespace) -> RuntimeSettings:
    config, base_dir = load_config(getattr(args, "config", None))
    agent_name = getattr(args, "name", None) or get_config_value(config, "agent_name", "name")
    hub_http = _normalize_hub_http(get_config_value(config, "hub_http"))
    hub_ws = _resolve_hub_ws(
        getattr(args, "hub", None) or get_config_value(config, "hub_ws", "hub"),
        hub_http=hub_http,
    )
    token = getattr(args, "token", None)
    if token is None:
        token = get_config_value(config, "token")

    inbox_dir = resolve_config_path(
        base_dir,
        getattr(args, "inbox_dir", None) or get_config_value(config, "inbox_dir", "inbox"),
    )
    outbox_dir = resolve_config_path(
        base_dir,
        getattr(args, "outbox_dir", None) or get_config_value(config, "outbox_dir", "outbox"),
    )
    sent_dir = resolve_config_path(
        base_dir,
        getattr(args, "sent_dir", None) or get_config_value(config, "sent_dir", "sent"),
    )

    if agent_name is None:
        raise ValueError("name is required (via --name or config)")
    if hub_ws is None:
        default_hub_ws = _default_hub_ws()
        if default_hub_ws:
            raise ValueError(
                f"hub websocket URL is required (via --hub or config). Distribution default is {default_hub_ws}."
            )
        raise ValueError("hub websocket URL is required (via --hub or config).")

    return RuntimeSettings(
        agent_name=str(agent_name),
        hub_ws=str(hub_ws),
        token=None if token is None else str(token),
        inbox_dir=(inbox_dir or Path(f"./inbox/{agent_name}")).resolve(),
        outbox_dir=(outbox_dir or Path(f"./outbox/{agent_name}")).resolve(),
        sent_dir=(sent_dir or Path(f"./sent/{agent_name}")).resolve(),
        poll_ms=int(getattr(args, "poll_ms", None) or get_config_value(config, "poll_ms", "pollMs") or DEFAULT_POLL_MS),
        backoff=parse_backoff_value(getattr(args, "backoff", None) or get_config_value(config, "backoff")),
        connect_timeout=float(
            getattr(args, "connect_timeout", None)
            or get_config_value(config, "connect_timeout", "connectTimeout")
            or 10.0
        ),
    )


def resolve_send_settings(args: argparse.Namespace) -> SendSettings:
    command_name = getattr(args, "command", "send")
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=command_name,
    )
    config, base_dir = load_config(str(config_path))
    outbox_dir = resolve_config_path(
        base_dir,
        getattr(args, "outbox_dir", None) or get_config_value(config, "outbox_dir", "outbox"),
    )
    if outbox_dir is None:
        raise ValueError("outbox directory is required (via --outbox-dir or config)")
    return SendSettings(outbox_dir=outbox_dir.resolve())


def resolve_hub_agent_settings(args: argparse.Namespace, *, require_hub_http: bool = True) -> HubAgentSettings:
    command_name = getattr(args, "command", "acp")
    if command_name == "runner":
        command_name = f"runner {getattr(args, 'runner_command', '')}".strip()
    if command_name == "chief":
        command_name = f"chief {getattr(args, 'chief_command', '')}".strip()
    allow_missing_config = command_name in {
        "runner start",
        "runner once",
        "onboard",
        "managed-start",
        "managed-join",
        "managed-close",
        "connect",
        "coordinate",
        "invite",
    } and (
        isinstance(getattr(args, "config", None), str) and getattr(args, "config", "").strip()
        or isinstance(getattr(args, "agent", None), str) and getattr(args, "agent", "").strip()
    )
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None) or getattr(args, "name", None),
        command_name=command_name,
        allow_missing_agent_config=bool(allow_missing_config),
    )
    if config_path.is_file():
        config, base_dir = load_config(str(config_path))
    elif allow_missing_config:
        config, base_dir = {}, config_path.parent
    else:
        config, base_dir = load_config(str(config_path))
    agent_name = getattr(args, "agent", None) or getattr(args, "name", None) or get_config_value(config, "agent_name", "name")
    hub_http = _normalize_hub_http(getattr(args, "hub_http", None) or get_config_value(config, "hub_http"))
    hub_ws = _resolve_hub_ws(getattr(args, "hub_ws", None) or get_config_value(config, "hub_ws", "hub"), hub_http=hub_http)
    token = getattr(args, "token", None)
    if token is None:
        token = get_config_value(config, "token")
    session_id = get_config_value(config, "session_id")
    member_token = get_config_value(config, "member_token")
    dashboard_session_path = _normalize_dashboard_session_path(get_config_value(config, "dashboard_session_path")) or "/dashboard/session"

    if not isinstance(agent_name, str) or not agent_name.strip():
        raise ValueError("agent_name is required (via --name or config)")
    if not hub_http:
        local_hub_http = resolve_local_hub_http()
        if local_hub_http:
            hub_http = local_hub_http
            hub_ws = _resolve_hub_ws(hub_ws, hub_http=hub_http)
    if require_hub_http and not hub_http:
        default_hub_http = _default_hub_http()
        if default_hub_http:
            raise ValueError(
                f"hub_http is required (via --hub-http or config). Distribution default is {default_hub_http}."
            )
        raise ValueError("hub_http is required (via --hub-http or config).")

    return HubAgentSettings(
        config_path=config_path,
        config=config,
        base_dir=base_dir or config_path.parent,
        agent_name=agent_name.strip(),
        hub_http=hub_http,
        hub_ws=hub_ws,
        token=token.strip() if isinstance(token, str) and token.strip() else None,
        session_id=session_id.strip() if isinstance(session_id, str) and session_id.strip() else None,
        member_token=member_token.strip() if isinstance(member_token, str) and member_token.strip() else None,
        dashboard_session_path=dashboard_session_path,
    )


def derive_hub_agent_settings(*, settings: HubAgentSettings, config: dict[str, Any]) -> HubAgentSettings:
    hub_http_value = _normalize_hub_http(get_config_value(config, "hub_http")) or settings.hub_http
    token_value = get_config_value(config, "token")
    session_id_value = get_config_value(config, "session_id")
    member_token_value = get_config_value(config, "member_token")
    dashboard_session_path_value = (
        _normalize_dashboard_session_path(get_config_value(config, "dashboard_session_path"))
        or settings.dashboard_session_path
    )
    return HubAgentSettings(
        config_path=settings.config_path,
        config=config,
        base_dir=settings.base_dir,
        agent_name=str(get_config_value(config, "agent_name", "name") or settings.agent_name).strip(),
        hub_http=hub_http_value,
        hub_ws=_resolve_hub_ws(get_config_value(config, "hub_ws", "hub"), hub_http=hub_http_value),
        token=token_value.strip() if isinstance(token_value, str) and token_value.strip() else settings.token,
        session_id=session_id_value.strip()
        if isinstance(session_id_value, str) and session_id_value.strip()
        else settings.session_id,
        member_token=member_token_value.strip()
        if isinstance(member_token_value, str) and member_token_value.strip()
        else settings.member_token,
        dashboard_session_path=dashboard_session_path_value,
    )


def resolve_agent_queue_dir(settings: HubAgentSettings, *keys: str, fallback: str) -> Path:
    raw_value = get_config_value(settings.config, *keys)
    resolved = resolve_config_path(settings.base_dir, raw_value)
    if resolved is not None:
        return resolved
    return (settings.base_dir / fallback).resolve()


def build_session_dashboard_url(
    *,
    hub_http: str,
    session_id: str,
    agent_name: str,
    member_token: str,
    dashboard_path: str = "/dashboard/session",
) -> str:
    query = urllib.parse.urlencode(
        {
            "session_id": session_id,
            "agent_name": agent_name,
        }
    )
    fragment = urllib.parse.urlencode({"member_token": member_token})
    return f"{hub_http.rstrip('/')}{dashboard_path}?{query}#{fragment}"


def build_session_dashboard_url_template(
    *,
    hub_http: str,
    session_id: str,
    dashboard_path: str = "/dashboard/session",
) -> str:
    query = urllib.parse.urlencode(
        {
            "session_id": session_id,
            "agent_name": "<agent_name>",
        }
    )
    fragment = urllib.parse.urlencode({"member_token": "<member_token>"})
    return f"{hub_http.rstrip('/')}{dashboard_path}?{query}#{fragment}"


def build_shareable_session_access(
    *,
    settings: HubAgentSettings,
    session_id: str,
    join_code: str | None,
    member_token: str,
    member_role: str | None,
) -> dict[str, Any]:
    shareable: dict[str, Any] = {
        "distribution_id": _distribution_id(),
        "session_id": session_id,
        "hub_http": settings.hub_http,
        "dashboard_session_path": settings.dashboard_session_path,
        "dashboard_session_url_template": build_session_dashboard_url_template(
            hub_http=settings.hub_http,
            session_id=session_id,
            dashboard_path=settings.dashboard_session_path,
        ),
        "shareable_dashboard_url_template": build_session_dashboard_url_template(
            hub_http=settings.hub_http,
            session_id=session_id,
            dashboard_path=settings.dashboard_session_path,
        ),
        "wait_command_example": "python ACP_AGENT/acp.py wait --config ACP_AGENT/agents/<agent>.json",
        "listen_command_example": "python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json",
        "heartbeat_command_example": "python ACP_AGENT/acp.py heartbeat --config ACP_AGENT/agents/<agent>.json",
        "busy_hold_command_example": (
            "python ACP_AGENT/acp.py status --config ACP_AGENT/agents/<agent>.json "
            "--state busy --text \"working on task\" --heartbeat-window-minutes 30"
        ),
        "long_task_payload_convention": "Prefix long TASK payloads with [long] or [busy-hold:30] so receivers can auto-start busy heartbeats.",
        "session_info_command_example": "python ACP_AGENT/acp.py session-info --config ACP_AGENT/agents/<agent>.json",
    }
    default_hub_http = _default_hub_http()
    if default_hub_http:
        shareable["official_hub_http"] = default_hub_http
        shareable["default_hub_http"] = default_hub_http
    if settings.hub_ws:
        shareable["hub_ws"] = settings.hub_ws
    default_hub_ws = _default_hub_ws()
    if default_hub_ws:
        shareable["default_hub_ws"] = default_hub_ws
    if join_code:
        shareable["join_code"] = join_code
        shareable["join_command_example"] = (
            "python ACP_AGENT/acp.py join-session "
            f"--config ACP_AGENT/agents/<agent>.json --code {join_code}"
        )
    if member_role:
        shareable["member_role"] = member_role
    return shareable


def _session_payload_value(payload: dict[str, Any], key: str) -> Any:
    direct_value = payload.get(key)
    if direct_value is not None:
        return direct_value
    nested_session = payload.get("session")
    if isinstance(nested_session, dict):
        return nested_session.get(key)
    return None


def _resolve_member_role(*, payload: dict[str, Any], agent_name: str) -> str | None:
    direct_role = _session_payload_value(payload, "member_role")
    if isinstance(direct_role, str) and direct_role.strip():
        return direct_role
    nested_session = payload.get("session")
    if not isinstance(nested_session, dict):
        return None
    members = nested_session.get("members")
    if not isinstance(members, list):
        return None
    for member in members:
        if not isinstance(member, dict):
            continue
        if member.get("agent_name") != agent_name:
            continue
        role = member.get("role")
        if isinstance(role, str) and role.strip():
            return role
    return None


def enrich_session_payload(
    *,
    settings: HubAgentSettings,
    payload: dict[str, Any],
    session_id: str,
    member_token: str,
    join_code: str | None,
    member_role: str | None,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["distribution_id"] = _distribution_id()
    enriched["hub_http"] = settings.hub_http
    default_hub_http = _default_hub_http()
    if default_hub_http:
        enriched["official_hub_http"] = default_hub_http
        enriched["default_hub_http"] = default_hub_http
    if settings.hub_ws:
        enriched["hub_ws"] = settings.hub_ws
    default_hub_ws = _default_hub_ws()
    if default_hub_ws:
        enriched["default_hub_ws"] = default_hub_ws
    enriched["session_dashboard_url"] = build_session_dashboard_url(
        hub_http=settings.hub_http,
        session_id=session_id,
        agent_name=settings.agent_name,
        member_token=member_token,
        dashboard_path=settings.dashboard_session_path,
    )
    enriched["current_member_dashboard_url"] = enriched["session_dashboard_url"]
    enriched["session_dashboard_url_template"] = build_session_dashboard_url_template(
        hub_http=settings.hub_http,
        session_id=session_id,
        dashboard_path=settings.dashboard_session_path,
    )
    enriched["shareable_dashboard_url_template"] = enriched["session_dashboard_url_template"]
    enriched["shareable_session_access"] = build_shareable_session_access(
        settings=settings,
        session_id=session_id,
        join_code=join_code,
        member_token=member_token,
        member_role=member_role,
    )
    enriched["operational_status"] = "waiting"
    enriched["listen_command_example"] = (
        f"python ACP_AGENT/acp.py listen --config {settings.config_path.as_posix()}"
    )
    enriched["interactive_listen_command_example"] = (
        f"python ACP_AGENT/acp.py listen --config {settings.config_path.as_posix()} "
        "--stop-after-message --timeout-seconds 300"
    )
    enriched["recommended_next_step"] = (
        "If you are a turn-based LLM agent that must execute work, use "
        "listen --stop-after-message in a loop. Use persistent listen only for daemons/runners."
    )
    enriched["next_steps"] = [
        "Turn-based executor loop: listen --stop-after-message --timeout-seconds 300, process one message, send REPLY/INFO, then listen again.",
        "Daemon/runner mode only: use persistent listen or runner start when another process can keep waiting without blocking the LLM turn.",
        "Share join_code, hub_http, and the shareable_dashboard_url_template with collaborators.",
        "Each collaborator should join the session, then use their own member_token to open the session dashboard.",
        "Publish waiting while available and busy while executing. If local work is complete but the next step depends on external instructions, hold a foreground wait-window before ending the turn (each Hub long-poll max 300s).",
        "If release_update.status is update_available, update between turns with self-update --auto-when-idle; tracked ACP_AGENT folders require explicit/manual update.",
        "If a task will keep the agent busy for a while, use status --state busy with --heartbeat-window-minutes so the Hub keeps the session liveness fresh.",
    ]
    return enriched


def write_config(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, payload)


def clear_session_credentials(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    updated = dict(config)
    updated.pop("session_id", None)
    updated.pop("member_token", None)
    updated.pop("join_code", None)
    updated.pop("member_role", None)
    write_config(path, updated)
    return updated


def _is_stale_session_binding_error(message: str) -> bool:
    return any(
        marker in message
        for marker in (
            "session does not exist",
            "agent is not a member of this session",
            "member token is invalid",
            "session closed because the chief left",
            "session closed because the last member left",
            "you left the session",
            "you were disconnected from the session",
            "session closed by admin",
            "session access is no longer available",
        )
    )


def ensure_detached_session_bootstrap(settings: HubAgentSettings, *, command_name: str) -> HubAgentSettings:
    if settings.session_id is None or settings.member_token is None:
        return settings

    route = (
        f"/sessions/{settings.session_id}"
        f"?agent_name={urllib.parse.quote(settings.agent_name)}"
        f"&member_token={urllib.parse.quote(settings.member_token)}"
    )
    try:
        snapshot = get_json(hub_http=settings.hub_http, route=route, token=settings.token)
    except ValueError as exc:
        message = str(exc)
        if _is_stale_session_binding_error(message):
            updated = clear_session_credentials(settings.config_path, settings.config)
            return derive_hub_agent_settings(settings=settings, config=updated)
        raise ValueError(
            f"{command_name} requires a detached config, but the current session binding could not be verified: {message}"
        ) from exc

    active_role = _resolve_member_role(payload=snapshot, agent_name=settings.agent_name) or settings.config.get("member_role")
    role_label = active_role if isinstance(active_role, str) and active_role.strip() else "member"
    raise ValueError(
        f"{command_name} cannot reuse {settings.config_path.name} because it is already attached to active session "
        f"{settings.session_id} as {settings.agent_name} ({role_label}). Use a different agent config or run leave-session first."
    )


def emit_json_line(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def _http_headers(*, token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-ACP-Token"] = token
    return headers


def _managed_agent_headers(agent_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {agent_token}",
    }


def request_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 310.0,
    retry_transient: bool = False,
    retry_backoff_seconds: tuple[float, ...] = TRANSIENT_RETRY_BACKOFF_SECONDS,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
    attempts = 1 + (len(retry_backoff_seconds) if retry_transient else 0)
    last_transient_body: str | None = None
    last_transient_code: int | None = None
    for attempt_index in range(attempts):
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers or {"Content-Type": "application/json"},
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            if (
                retry_transient
                and exc.code in TRANSIENT_HTTP_STATUS_CODES
                and attempt_index < attempts - 1
            ):
                last_transient_code = exc.code
                last_transient_body = response_body
                time.sleep(max(float(retry_backoff_seconds[attempt_index]), 0.0))
                continue
            if exc.code == 409 and ("WAIT_ALREADY_ACTIVE" in response_body or "active wait" in response_body):
                raise ValueError(
                    f"hub HTTP 409: {response_body}\n"
                    f"Action: do not run concurrent waits. Stop the existing managed-join/listen/wait process, then use: {TURN_BASED_LISTEN_COMMAND}"
                ) from exc
            if retry_transient and exc.code in TRANSIENT_HTTP_STATUS_CODES:
                raise ValueError(
                    f"hub HTTP {exc.code}: {response_body}\n"
                    f"Action: transient Hub/gateway failure persisted after {attempts} attempts."
                ) from exc
            raise ValueError(f"hub HTTP {exc.code}: {response_body}") from exc
    raise ValueError(
        f"hub HTTP {last_transient_code}: {last_transient_body}\n"
        f"Action: transient Hub/gateway failure persisted after {attempts} attempts."
    )


def managed_agent_token_from_args(args: argparse.Namespace, config: dict[str, Any] | None = None) -> str:
    raw_token = getattr(args, "agent_token", None)
    if not (isinstance(raw_token, str) and raw_token.strip()) and isinstance(config, dict):
        raw_token = get_config_value(config, "managed_agent_token", "agent_token")
    if isinstance(raw_token, str) and raw_token.strip():
        return raw_token.strip()
    raise ValueError("agent_token is required. Pass --agent-token <TOKEN> or select a config with managed_agent_token.")


def managed_command_hub_http_from_args(args: argparse.Namespace, *, command_name: str) -> tuple[str, dict[str, Any]]:
    try:
        settings = resolve_hub_agent_settings(args)
        return settings.hub_http, settings.config
    except ValueError as exc:
        raw_hub_http = getattr(args, "hub_http", None)
        hub_http = _normalize_hub_http(raw_hub_http)
        if hub_http:
            return hub_http, {}
        raise ValueError(
            f"{exc}\n"
            f"Action: {command_name} can run without choosing one config when you pass "
            f"--hub-http <HUB> --agent-token <TOKEN>. If you want config defaults, pass --agent <name> or --config <path>."
        ) from exc


def post_json(*, hub_http: str, route: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    return request_json(
        method="POST",
        url=f"{hub_http.rstrip('/')}{route}",
        payload=payload,
        headers=_http_headers(token=token),
        timeout_seconds=310.0,
        retry_transient=route in TRANSIENT_RETRY_SAFE_POST_ROUTES,
    )


def get_json(*, hub_http: str, route: str, token: str | None = None) -> dict[str, Any]:
    return request_json(
        method="GET",
        url=f"{hub_http.rstrip('/')}{route}",
        payload=None,
        headers=_http_headers(token=token),
        timeout_seconds=30.0,
        retry_transient=True,
    )


def ensure_queue_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_json_atomic(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=destination.parent, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(destination)


def append_inbound_message(inbox_dir: Path, payload: dict[str, Any]) -> Path:
    ensure_queue_dirs(inbox_dir)
    msg_id = str(payload.get("id", uuid4()))
    ts = str(payload.get("ts", utc_now_rfc3339())).replace(":", "-")
    path = inbox_dir / f"{safe_name(ts)}__{safe_name(msg_id)}.json"
    write_json_atomic(path, payload)
    return path


def enqueue_outbound_message(outbox_dir: Path, payload: dict[str, Any]) -> Path:
    ensure_queue_dirs(outbox_dir)
    msg_id = str(payload.get("id") or uuid4())
    enriched = dict(payload)
    enriched["id"] = msg_id
    enriched.setdefault("ts", utc_now_rfc3339())
    ts = str(enriched["ts"]).replace(":", "-")
    path = outbox_dir / f"{safe_name(ts)}__{safe_name(msg_id)}.json"
    write_json_atomic(path, enriched)
    return path


def list_outbound_messages(outbox_dir: Path) -> list[Path]:
    if not outbox_dir.exists():
        return []
    return sorted(path for path in outbox_dir.iterdir() if path.is_file() and path.suffix.lower() == ".json")


def load_json_object(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return parsed


def build_outbound_envelope(*, agent_name: str, record: dict[str, Any]) -> dict[str, Any]:
    recipient = record.get("to")
    action = record.get("action")
    payload = record.get("payload")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("outbound record is missing a valid 'to' field")
    if not isinstance(action, str) or action not in VALID_ACTIONS:
        raise ValueError("outbound record is missing a valid 'action' field")
    if not isinstance(payload, str):
        raise ValueError("outbound record is missing a valid 'payload' field")

    envelope: dict[str, Any] = {
        "type": "MSG",
        "id": record.get("id") if isinstance(record.get("id"), str) and record.get("id") else str(uuid4()),
        "ts": record.get("ts") if isinstance(record.get("ts"), str) and record.get("ts") else utc_now_rfc3339(),
        "from": agent_name,
        "to": recipient.strip(),
        "action": action,
        "payload": payload,
    }
    if isinstance(record.get("thread_id"), str) and record["thread_id"]:
        envelope["thread_id"] = record["thread_id"]
    if isinstance(record.get("in_reply_to"), str) and record["in_reply_to"]:
        envelope["in_reply_to"] = record["in_reply_to"]
    return envelope


def archive_sent_message(source_path: Path, sent_dir: Path) -> Path:
    ensure_queue_dirs(sent_dir)
    destination = sent_dir / source_path.name
    if destination.exists():
        destination = sent_dir / f"{source_path.stem}__{uuid4().hex}{source_path.suffix}"
    source_path.replace(destination)
    return destination


async def send_json_frame(websocket: LiveSocketAdapter, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload))


async def receive_json_frame(websocket: LiveSocketAdapter) -> dict[str, Any]:
    frame = json.loads(await websocket.receive_text())
    if not isinstance(frame, dict):
        raise ValueError("websocket payload must decode to JSON object")
    return frame


async def register_hello(websocket: LiveSocketAdapter, *, name: str, token: str | None = None) -> None:
    envelope: dict[str, Any] = {"type": "HELLO", "role": "agent", "name": name}
    if token:
        envelope["token"] = token
    await send_json_frame(websocket, envelope)


async def safe_close(websocket: LiveSocketAdapter) -> None:
    try:
        await websocket.close()
    except Exception:
        return


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in value.strip())
    cleaned = cleaned.strip("-")
    return cleaned or "msg"


def _join_text_parts(parts: Any) -> str | None:
    if not isinstance(parts, list):
        return None
    cleaned = " ".join(str(item).strip() for item in parts if str(item).strip()).strip()
    return cleaned or None


def _read_payload_file(path_value: str) -> str:
    if path_value == "-":
        return sys.stdin.read()
    return Path(path_value).read_text(encoding="utf-8")


def resolve_send_payload_text(args: argparse.Namespace) -> str:
    payload_file = getattr(args, "payload_file", None)
    if isinstance(payload_file, str) and payload_file.strip():
        file_text = _read_payload_file(payload_file.strip())
        if file_text.strip():
            return file_text
        raise ValueError("payload file is empty.")
    payload_value = getattr(args, "payload", None)
    if isinstance(payload_value, str) and payload_value.strip():
        return payload_value
    positional = _join_text_parts(getattr(args, "text", None))
    if positional is not None:
        return positional
    raise ValueError("payload is required.")


def resolve_structured_send_payload(args: argparse.Namespace) -> Any:
    payload_text = resolve_send_payload_text(args)
    task_id = getattr(args, "task_id", None)
    if not (isinstance(task_id, str) and task_id.strip()):
        return payload_text
    try:
        parsed = json.loads(payload_text)
    except (ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        payload = dict(parsed)
    else:
        action = str(getattr(args, "action", "") or "").upper()
        key = "instructions" if action == "TASK" else "summary"
        payload = {key: payload_text}
    payload["task_id"] = task_id.strip()
    return payload


def _listen_namespace_for_config(config_path: Path, *, stop_after_message: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        command="listen",
        config=str(config_path),
        agent=None,
        timeout_seconds=DEFAULT_LISTEN_TIMEOUT_SECONDS,
        retry_delay_seconds=2.0,
        stop_after_message=stop_after_message,
        auto_busy_heartbeat_minutes=0.0,
        auto_busy_heartbeat_interval_seconds=45.0,
        update_policy=None,
        manifest_url=None,
        allow_tracked_auto_update=False,
        emit=True,
    )


def emit_persistent_listen_warning(*, command_name: str, config_path: Path) -> None:
    print(
        f"{PERSISTENT_LISTEN_WARNING}\n"
        f"Command {command_name!r} is starting persistent listen for {config_path}. "
        "Use --listen-once or run the one-message listen command manually for turn-based agents.",
        file=sys.stderr,
        flush=True,
    )


def maybe_start_listen_after_session(*, config_path: Path, mode: str, command_name: str) -> None:
    if mode == "none":
        return
    if mode == "once":
        listen_for_session_message(_listen_namespace_for_config(config_path, stop_after_message=True))
        return
    if mode != "persistent":
        raise ValueError("listen mode must be one of: none, once, persistent.")
    emit_persistent_listen_warning(command_name=command_name, config_path=config_path)
    listen_for_session_message(_listen_namespace_for_config(config_path))


def _managed_join_listen_mode(args: argparse.Namespace) -> str:
    if bool(getattr(args, "listen_once", False)) and bool(getattr(args, "listen_persistent", False)):
        raise ValueError("Use only one of --listen-once or --listen-persistent.")
    if bool(getattr(args, "listen_once", False)):
        return "once"
    if bool(getattr(args, "listen_persistent", False)):
        return "persistent"
    return "none"


def build_send_record(args: argparse.Namespace) -> dict[str, Any]:
    record: dict[str, Any] = {"to": args.to, "action": args.action, "payload": resolve_send_payload_text(args)}
    if args.thread_id:
        record["thread_id"] = args.thread_id
    if args.in_reply_to:
        record["in_reply_to"] = args.in_reply_to
    return record


def build_session_send_payload(args: argparse.Namespace, settings: HubAgentSettings) -> dict[str, Any]:
    if settings.session_id is None:
        raise ValueError("session_id is required in config. Create or join a session first.")
    if settings.member_token is None:
        raise ValueError("member_token is required in config. Create or join a session first.")
    payload: dict[str, Any] = {
        "session_id": settings.session_id,
        "agent_name": settings.agent_name,
        "member_token": settings.member_token,
        "to": args.to,
        "action": args.action,
        "payload": resolve_structured_send_payload(args),
    }
    if args.thread_id:
        payload["thread_id"] = args.thread_id
    if args.in_reply_to:
        payload["in_reply_to"] = args.in_reply_to
    return payload


def _persist_session_binding(
    *,
    settings: HubAgentSettings,
    session_id: str,
    member_token: str,
    join_code: str | None,
    member_role: str | None,
    dashboard_session_path: str | None = None,
    hub_ws_override: str | None = None,
    managed_agent_token: str | None = None,
    capabilities: list[str] | None = None,
) -> HubAgentSettings:
    updated = dict(settings.config)
    updated["agent_name"] = settings.agent_name
    updated["hub_http"] = settings.hub_http
    hub_ws_value = hub_ws_override or settings.hub_ws or _derive_hub_ws_from_http(settings.hub_http)
    if hub_ws_value:
        updated["hub_ws"] = hub_ws_value
    updated["hub_mode"] = _hub_mode_for_http(settings.hub_http)
    updated["session_id"] = session_id
    updated["member_token"] = member_token
    updated["dashboard_session_path"] = dashboard_session_path or settings.dashboard_session_path
    if capabilities is not None:
        updated["capabilities"] = capabilities
    if isinstance(managed_agent_token, str) and managed_agent_token.strip():
        updated["managed_agent_token"] = managed_agent_token.strip()
    if join_code:
        updated["join_code"] = join_code
    if member_role:
        updated["member_role"] = member_role
    write_config(settings.config_path, updated)
    operational_settings = derive_hub_agent_settings(settings=settings, config=updated)
    safe_update_session_status(
        settings=operational_settings,
        state="waiting",
        text="waiting for session activity",
    )
    return operational_settings


def create_session_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = ensure_detached_session_bootstrap(
        resolve_hub_agent_settings(args),
        command_name="create-session",
    )
    response = post_json(
        hub_http=settings.hub_http,
        route="/sessions",
        payload={
            "agent_name": settings.agent_name,
            "title": args.title,
            "project": args.project,
            **({"capabilities": optional_capabilities_from_args_config(args, settings.config)} if optional_capabilities_from_args_config(args, settings.config) is not None else {}),
            "token": settings.token,
        },
        token=settings.token,
    )
    operational_settings = _persist_session_binding(
        settings=settings,
        session_id=response["session_id"],
        member_token=response["member_token"],
        join_code=response.get("join_code"),
        member_role=response.get("member_role"),
        dashboard_session_path="/dashboard/session",
        capabilities=optional_capabilities_from_args_config(args, settings.config),
    )
    return enrich_session_payload(
        settings=operational_settings,
        payload=response,
        session_id=response["session_id"],
        member_token=response["member_token"],
        join_code=response.get("join_code"),
        member_role=response.get("member_role"),
    )


def create_session_and_optionally_listen(args: argparse.Namespace, *, listen_after: bool) -> dict[str, Any]:
    payload = create_session_from_args(args)
    emit_json_line(payload)
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=getattr(args, "command", "create-session"),
    )
    maybe_start_listen_after_session(
        config_path=config_path,
        mode="persistent" if listen_after else "none",
        command_name=getattr(args, "command", "create-session"),
    )
    return payload


def join_session_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = ensure_detached_session_bootstrap(
        resolve_hub_agent_settings(args),
        command_name="join-session",
    )
    response = post_json(
        hub_http=settings.hub_http,
        route="/sessions/join",
        payload={
            "agent_name": settings.agent_name,
            "join_code": args.code,
            **({"capabilities": optional_capabilities_from_args_config(args, settings.config)} if optional_capabilities_from_args_config(args, settings.config) is not None else {}),
            "token": settings.token,
        },
        token=settings.token,
    )
    operational_settings = _persist_session_binding(
        settings=settings,
        session_id=response["session_id"],
        member_token=response["member_token"],
        join_code=response.get("join_code"),
        member_role=response.get("member_role"),
        dashboard_session_path="/dashboard/session",
        capabilities=optional_capabilities_from_args_config(args, settings.config),
    )
    return enrich_session_payload(
        settings=operational_settings,
        payload=response,
        session_id=response["session_id"],
        member_token=response["member_token"],
        join_code=response.get("join_code"),
        member_role=response.get("member_role"),
    )


def join_session_and_optionally_listen(args: argparse.Namespace, *, listen_after: bool) -> dict[str, Any]:
    payload = join_session_from_args(args)
    emit_json_line(payload)
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=getattr(args, "command", "join-session"),
    )
    maybe_start_listen_after_session(
        config_path=config_path,
        mode="persistent" if listen_after else "none",
        command_name=getattr(args, "command", "join-session"),
    )
    return payload


def _managed_workspace_slug_arg(args: argparse.Namespace) -> str | None:
    raw_value = getattr(args, "workspace", None)
    if not isinstance(raw_value, str):
        return None
    cleaned = raw_value.strip()
    return cleaned or None


def _managed_agent_route(*, workspace_slug: str | None, suffix: str = "") -> str:
    normalized_suffix = suffix if suffix.startswith("/") or not suffix else f"/{suffix}"
    if workspace_slug:
        return f"/managed/agent/workspaces/{urllib.parse.quote(workspace_slug, safe='')}{normalized_suffix}"
    return f"/managed/agent{normalized_suffix}"


def _onboard_managed_workspace_slug_arg(args: argparse.Namespace) -> str | None:
    raw_value = getattr(args, "managed_workspace", None)
    if not isinstance(raw_value, str):
        return None
    cleaned = raw_value.strip()
    return cleaned or None


def _read_project_id_file(workspace_path: Path) -> str | None:
    project_file = workspace_path / ".acp" / "project-id"
    if not project_file.is_file():
        return None
    value = project_file.read_text(encoding="utf-8").strip()
    return value or None


def derive_onboard_project_id(workspace_path: str | None, explicit_project: str | None = None) -> str:
    if isinstance(explicit_project, str) and explicit_project.strip():
        return explicit_project.strip()
    raw_workspace = workspace_path if isinstance(workspace_path, str) and workspace_path.strip() else "."
    workspace = Path(raw_workspace).expanduser().resolve()
    file_value = _read_project_id_file(workspace)
    if file_value:
        return file_value
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).name
    except (OSError, subprocess.SubprocessError):
        pass
    return workspace.name


def _managed_session_sort_key(session: dict[str, Any]) -> str:
    raw_created_at = session.get("created_at")
    return raw_created_at.strip() if isinstance(raw_created_at, str) else ""


def select_onboard_workspace_session(
    sessions: list[dict[str, Any]],
    *,
    session_id: str | None,
    project: str | None,
    prefer_latest: bool,
) -> dict[str, Any]:
    requested_session_id = session_id.strip() if isinstance(session_id, str) and session_id.strip() else None
    if requested_session_id:
        matches = [item for item in sessions if item.get("session_id") == requested_session_id]
        if not matches:
            raise ValueError(f"managed session {requested_session_id} was not found.")
        return matches[0]

    requested_project = project.strip() if isinstance(project, str) and project.strip() else None
    if requested_project:
        matches = [item for item in sessions if item.get("project") == requested_project]
    else:
        matches = list(sessions)
    if not matches:
        label = f"project {requested_project!r}" if requested_project else "any project"
        raise ValueError(f"no managed workspace session found for {label}.")
    if len(matches) == 1:
        return matches[0]
    if prefer_latest:
        return sorted(matches, key=_managed_session_sort_key)[-1]
    ids = ", ".join(str(item.get("session_id")) for item in matches)
    label = f"project {requested_project!r}" if requested_project else "available sessions"
    raise ValueError(f"multiple managed workspace sessions matched {label}: {ids}. Pass --session-id or --prefer-latest.")


def _extract_managed_sessions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        raw_sessions = payload.get("workspace_sessions")
    if not isinstance(raw_sessions, list):
        return []
    return [item for item in raw_sessions if isinstance(item, dict)]


def _onboard_selection_error_is_retryable(error: ValueError) -> bool:
    message = str(error)
    return message.startswith("no managed workspace session found") or (
        message.startswith("managed session ") and message.endswith(" was not found.")
    )


def _onboard_ready_payload(
    *,
    agent_name: str,
    project: str,
    role: str,
    capabilities: list[str],
    provider: str | None,
    workspace_path: str,
) -> dict[str, Any]:
    return {
        "type": "READY",
        "agent_name": agent_name,
        "project": project,
        "role": role,
        "capabilities": capabilities,
        "provider": provider,
        "workspace_path": workspace_path,
        "delivery_mode": "runner",
        "status": "available",
    }


def _onboard_runner_command(*, config_path: Path) -> list[str]:
    return [sys.executable, str((ACP_ROOT / "acp.py").resolve()), "runner", "start", "--config", str(config_path)]


def _managed_agent_bootstrap(*, hub_http: str, agent_token: str) -> dict[str, Any]:
    return request_json(
        method="GET",
        url=f"{hub_http.rstrip('/')}/managed/agent/bootstrap",
        payload=None,
        headers=_managed_agent_headers(agent_token),
        timeout_seconds=30.0,
    )


def managed_start_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = ensure_detached_session_bootstrap(
        resolve_hub_agent_settings(args),
        command_name="managed-start",
    )
    workspace_slug = _managed_workspace_slug_arg(args)
    agent_token = managed_agent_token_from_args(args, settings.config)
    capabilities = optional_capabilities_from_args_config(args, settings.config)
    response = request_json(
        method="POST",
        url=f"{settings.hub_http.rstrip('/')}{_managed_agent_route(workspace_slug=workspace_slug, suffix='/sessions')}",
        payload={
            "agent_name": settings.agent_name,
            "title": args.title,
            "project": args.project,
            **({"capabilities": capabilities} if capabilities is not None else {}),
        },
        headers=_managed_agent_headers(agent_token),
        timeout_seconds=310.0,
    )
    acp_session = response.get("acp_session")
    if not isinstance(acp_session, dict):
        raise ValueError("managed-start expected an acp_session object in the response.")
    operational_settings = _persist_session_binding(
        settings=settings,
        session_id=str(acp_session["session_id"]),
        member_token=str(acp_session["member_token"]),
        join_code=str(acp_session.get("join_code")) if acp_session.get("join_code") is not None else None,
        member_role=str(acp_session.get("member_role")) if acp_session.get("member_role") is not None else None,
        dashboard_session_path="/managed/dashboard/session",
        hub_ws_override=getattr(args, "hub_ws", None) or settings.hub_ws or _derive_hub_ws_from_http(settings.hub_http),
        managed_agent_token=agent_token,
        capabilities=capabilities,
    )
    enriched = enrich_session_payload(
        settings=operational_settings,
        payload=acp_session,
        session_id=str(acp_session["session_id"]),
        member_token=str(acp_session["member_token"]),
        join_code=str(acp_session.get("join_code")) if acp_session.get("join_code") is not None else None,
        member_role=str(acp_session.get("member_role")) if acp_session.get("member_role") is not None else None,
    )
    enriched["managed_workspace"] = response.get("workspace")
    enriched["managed_workspace_session"] = response.get("workspace_session")
    enriched["managed_agent_token"] = response.get("agent_token")
    if response.get("workspace") is not None:
        enriched["managed_workspace_slug"] = response["workspace"].get("slug") if isinstance(response["workspace"], dict) else None
    enriched["managed_command"] = "managed-start"
    return enriched


def managed_join_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = ensure_detached_session_bootstrap(
        resolve_hub_agent_settings(args),
        command_name="managed-join",
    )
    workspace_slug = _managed_workspace_slug_arg(args)
    agent_token = managed_agent_token_from_args(args, settings.config)
    capabilities = optional_capabilities_from_args_config(args, settings.config)
    session_id = str(args.session_id).strip()
    if not session_id:
        raise ValueError("session_id is required.")
    managed_join_suffix = f"/sessions/{urllib.parse.quote(session_id, safe='')}/join"
    response = request_json(
        method="POST",
        url=f"{settings.hub_http.rstrip('/')}{_managed_agent_route(workspace_slug=workspace_slug, suffix=managed_join_suffix)}",
        payload={"agent_name": settings.agent_name, **({"capabilities": capabilities} if capabilities is not None else {})},
        headers=_managed_agent_headers(agent_token),
        timeout_seconds=310.0,
    )
    acp_session = response.get("acp_session")
    if not isinstance(acp_session, dict):
        raise ValueError("managed-join expected an acp_session object in the response.")
    operational_settings = _persist_session_binding(
        settings=settings,
        session_id=session_id,
        member_token=str(acp_session["member_token"]),
        join_code=str(acp_session.get("join_code")) if acp_session.get("join_code") is not None else None,
        member_role=str(acp_session.get("member_role")) if acp_session.get("member_role") is not None else None,
        dashboard_session_path="/managed/dashboard/session",
        hub_ws_override=getattr(args, "hub_ws", None) or settings.hub_ws or _derive_hub_ws_from_http(settings.hub_http),
        managed_agent_token=agent_token,
        capabilities=capabilities,
    )
    enriched = enrich_session_payload(
        settings=operational_settings,
        payload=acp_session,
        session_id=session_id,
        member_token=str(acp_session["member_token"]),
        join_code=str(acp_session.get("join_code")) if acp_session.get("join_code") is not None else None,
        member_role=str(acp_session.get("member_role")) if acp_session.get("member_role") is not None else None,
    )
    enriched["managed_workspace"] = response.get("workspace")
    enriched["managed_workspace_session"] = response.get("workspace_session")
    enriched["managed_agent_token"] = response.get("agent_token")
    if response.get("workspace") is not None:
        enriched["managed_workspace_slug"] = response["workspace"].get("slug") if isinstance(response["workspace"], dict) else None
    enriched["managed_command"] = "managed-join"
    return enriched


def managed_start_and_optionally_listen(args: argparse.Namespace, *, listen_after: bool) -> dict[str, Any]:
    payload = managed_start_from_args(args)
    emit_json_line(payload)
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=getattr(args, "command", "managed-start"),
    )
    maybe_start_listen_after_session(
        config_path=config_path,
        mode="persistent" if listen_after else "none",
        command_name=getattr(args, "command", "managed-start"),
    )
    return payload


def managed_join_and_optionally_listen(args: argparse.Namespace, *, listen_mode: str) -> dict[str, Any]:
    payload = managed_join_from_args(args)
    emit_json_line(payload)
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=getattr(args, "command", "managed-join"),
    )
    maybe_start_listen_after_session(
        config_path=config_path,
        mode=listen_mode,
        command_name=getattr(args, "command", "managed-join"),
    )
    return payload


def managed_sessions_from_args(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, config = managed_command_hub_http_from_args(args, command_name="managed-sessions")
    workspace_slug = _managed_workspace_slug_arg(args)
    agent_token = managed_agent_token_from_args(args, config)
    response = request_json(
        method="GET",
        url=f"{hub_http.rstrip('/')}{_managed_agent_route(workspace_slug=workspace_slug, suffix='/sessions')}",
        payload=None,
        headers=_managed_agent_headers(agent_token),
        timeout_seconds=30.0,
    )
    if response.get("workspace") is not None:
        response["managed_workspace_slug"] = response["workspace"].get("slug") if isinstance(response["workspace"], dict) else None
    response["managed_command"] = "managed-sessions"
    return response


def onboard_from_args(args: argparse.Namespace) -> dict[str, Any]:
    role = getattr(args, "role", "worker")
    if role != "worker":
        raise ValueError("onboard currently supports --role worker. Autonomous chief is a separate follow-up flow.")

    settings = resolve_hub_agent_settings(args)
    agent_token = managed_agent_token_from_args(args, settings.config)
    capabilities = optional_capabilities_from_args_config(args, settings.config)
    workspace_path = normalize_workspace_path(getattr(args, "workspace", None) or ".")
    project_id = derive_onboard_project_id(workspace_path, getattr(args, "project", None))
    workspace_slug = _onboard_managed_workspace_slug_arg(args)
    _managed_agent_bootstrap(hub_http=settings.hub_http, agent_token=agent_token)

    deadline = time.monotonic() + max(float(getattr(args, "wait_for_session", 0.0) or 0.0), 0.0)
    selected_session: dict[str, Any] | None = None
    sessions_payload: dict[str, Any] = {}
    last_error: ValueError | None = None
    while True:
        sessions_payload = managed_sessions_from_args(
            argparse.Namespace(
                command="managed-sessions",
                config=getattr(args, "config", None),
                agent=getattr(args, "agent", None),
                hub_http=getattr(args, "hub_http", None),
                token=getattr(args, "token", None),
                workspace=workspace_slug,
                agent_token=agent_token,
            )
        )
        try:
            selected_session = select_onboard_workspace_session(
                _extract_managed_sessions(sessions_payload),
                session_id=getattr(args, "session_id", None),
                project=project_id,
                prefer_latest=bool(getattr(args, "prefer_latest", False)),
            )
            break
        except ValueError as exc:
            last_error = exc
            if not _onboard_selection_error_is_retryable(exc):
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(2.0, max(deadline - time.monotonic(), 0.1)))

    if selected_session is None:
        raise last_error or ValueError("no managed workspace session was selected.")
    session_id = selected_session.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("selected managed workspace session does not include session_id.")

    join_payload = managed_join_from_args(
        argparse.Namespace(
            command="managed-join",
            config=getattr(args, "config", None),
            agent=getattr(args, "agent", None),
            hub_http=getattr(args, "hub_http", None),
            hub_ws=getattr(args, "hub_ws", None),
            token=getattr(args, "token", None),
            workspace=workspace_slug,
            agent_token=agent_token,
            session_id=session_id,
            **({"capabilities": ",".join(capabilities)} if capabilities is not None else {}),
            no_listen=True,
            listen_once=False,
            listen_persistent=False,
        )
    )
    operational_settings = resolve_hub_agent_settings(
        argparse.Namespace(command="onboard", config=getattr(args, "config", None), agent=getattr(args, "agent", None))
    )

    provider = getattr(args, "provider", None) or get_config_value(operational_settings.config, "runner_provider", "provider")
    if not isinstance(provider, str) or not provider.strip():
        provider = "claude_local"

    ready_sent = False
    ready_result: dict[str, Any] | None = None
    ready_recipient = getattr(args, "to", None) or selected_session.get("owner_agent_name")
    if (
        not bool(getattr(args, "skip_ready", False))
        and isinstance(ready_recipient, str)
        and ready_recipient.strip()
        and ready_recipient.strip() != operational_settings.agent_name
    ):
        ready_result = post_json(
            hub_http=operational_settings.hub_http,
            route="/sessions/send",
            payload={
                "session_id": operational_settings.session_id,
                "agent_name": operational_settings.agent_name,
                "member_token": operational_settings.member_token,
                "to": ready_recipient.strip(),
                "action": "INFO",
                "payload": _onboard_ready_payload(
                    agent_name=operational_settings.agent_name,
                    project=project_id,
                    role=role,
                    capabilities=capabilities or [],
                    provider=provider,
                    workspace_path=workspace_path,
                ),
            },
            token=operational_settings.token,
        )
        ready_sent = True

    runner_args = argparse.Namespace(
        command="runner",
        runner_command="start",
        config=str(operational_settings.config_path),
        agent=None,
        hub_http=None,
        hub_ws=None,
        token=None,
        provider=provider,
        workspace=workspace_path,
        session_id=None,
        member_token=None,
        join_code=None,
        wait_timeout_seconds=getattr(args, "wait_timeout_seconds", 120.0),
        task_timeout_seconds=getattr(args, "task_timeout_seconds", 1800.0),
        retry_delay_seconds=getattr(args, "retry_delay_seconds", 2.0),
    )
    profile = bootstrap_runner_session(runner_args, command_name="onboard")
    operational_settings = profile["settings"]
    publish_runner_waiting(settings=operational_settings, profile=profile, text="onboarded and waiting for TASK")

    payload: dict[str, Any] = {
        "status": "onboarded",
        "managed_command": "onboard",
        "agent_name": operational_settings.agent_name,
        "session_id": operational_settings.session_id,
        "project": project_id,
        "selected_session": selected_session,
        "managed_workspace_slug": sessions_payload.get("managed_workspace_slug"),
        "config_path": str(operational_settings.config_path),
        "runner_provider": profile["provider"],
        "runner_workspace": profile["workspace_path"],
        "capabilities": capabilities or [],
        "ready_sent": ready_sent,
        "ready_to": ready_recipient if isinstance(ready_recipient, str) else None,
        "ready_result": ready_result,
        "join_result": join_payload,
        "runner_command": _onboard_runner_command(config_path=operational_settings.config_path),
    }
    if bool(getattr(args, "start_runner", False)):
        emit_json_line(payload)
        return runner_start(runner_args)
    return payload


def _connect_chief_command(*, config_path: Path, backlog_dir: str | None = None) -> list[str]:
    command = [sys.executable, str((ACP_ROOT / "acp.py").resolve()), "chief", "start", "--config", str(config_path)]
    if isinstance(backlog_dir, str) and backlog_dir.strip():
        command.extend(["--backlog-dir", backlog_dir.strip()])
    return command


def connect_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    requested_role = str(getattr(args, "role", "auto") or "auto").strip().lower()
    member_role = str(get_config_value(settings.config, "member_role") or "").strip().lower()

    if requested_role in {"auto", "chief"} and settings.session_id and settings.member_token and member_role == "chief":
        command = _connect_chief_command(config_path=settings.config_path, backlog_dir=getattr(args, "backlog_dir", None))
        payload: dict[str, Any] = {
            "status": "connected",
            "connect_role": "chief",
            "agent_name": settings.agent_name,
            "session_id": settings.session_id,
            "explanation": "Existing config is the session chief; use chief start to coordinate backlog.",
            "chief_command": command,
        }
        if bool(getattr(args, "start_chief", False)):
            emit_json_line(payload)
            return chief_start(
                argparse.Namespace(
                    command="chief",
                    chief_command="start",
                    config=str(settings.config_path),
                    agent=None,
                    hub_http=None,
                    hub_ws=None,
                    token=None,
                    backlog_dir=getattr(args, "backlog_dir", None),
                    workspace=getattr(args, "workspace", None),
                    provider=getattr(args, "provider", None),
                    wait_timeout_seconds=getattr(args, "wait_timeout_seconds", 30.0),
                    tick_seconds=2.0,
                    once=False,
                )
            )
        return payload

    if requested_role == "chief":
        if settings.session_id and settings.member_token:
            raise ValueError("connect --role chief needs a chief config; current config is not marked as member_role=chief.")
        start_payload = managed_start_from_args(
            argparse.Namespace(
                command="managed-start",
                config=getattr(args, "config", None),
                agent=getattr(args, "agent", None),
                hub_http=getattr(args, "hub_http", None),
                hub_ws=getattr(args, "hub_ws", None),
                token=getattr(args, "token", None),
                workspace=getattr(args, "managed_workspace", None),
                agent_token=getattr(args, "agent_token", None),
                title=getattr(args, "project", None) or "ACP coordination",
                project=getattr(args, "project", None),
                capabilities=getattr(args, "capabilities", None),
                no_listen=True,
            )
        )
        operational_settings = resolve_hub_agent_settings(
            argparse.Namespace(command="connect", config=getattr(args, "config", None), agent=getattr(args, "agent", None))
        )
        command = _connect_chief_command(config_path=operational_settings.config_path, backlog_dir=getattr(args, "backlog_dir", None))
        start_payload["connect_role"] = "chief"
        start_payload["explanation"] = "Created managed session as chief; use chief start to coordinate backlog."
        start_payload["chief_command"] = command
        if bool(getattr(args, "start_chief", False)):
            emit_json_line(start_payload)
            return chief_start(
                argparse.Namespace(
                    command="chief",
                    chief_command="start",
                    config=str(operational_settings.config_path),
                    agent=None,
                    hub_http=None,
                    hub_ws=None,
                    token=None,
                    backlog_dir=getattr(args, "backlog_dir", None),
                    workspace=getattr(args, "workspace", None),
                    provider=getattr(args, "provider", None),
                    wait_timeout_seconds=getattr(args, "wait_timeout_seconds", 30.0),
                    tick_seconds=2.0,
                    once=False,
                )
            )
        return start_payload

    payload = onboard_from_args(
        argparse.Namespace(
            command="onboard",
            config=getattr(args, "config", None),
            agent=getattr(args, "agent", None),
            hub_http=getattr(args, "hub_http", None),
            hub_ws=getattr(args, "hub_ws", None),
            workspace=getattr(args, "workspace", None),
            managed_workspace=getattr(args, "managed_workspace", None),
            agent_token=getattr(args, "agent_token", None),
            session_id=getattr(args, "session_id", None),
            project=getattr(args, "project", None),
            role="worker",
            capabilities=getattr(args, "capabilities", None),
            provider=getattr(args, "provider", None),
            wait_for_session=getattr(args, "wait_for_session", 120.0),
            prefer_latest=getattr(args, "prefer_latest", False),
            to=None,
            skip_ready=getattr(args, "skip_ready", False),
            start_runner=getattr(args, "start_runner", False),
            wait_timeout_seconds=getattr(args, "wait_timeout_seconds", 120.0),
            task_timeout_seconds=getattr(args, "task_timeout_seconds", 1800.0),
            retry_delay_seconds=getattr(args, "retry_delay_seconds", 2.0),
        )
    )
    payload["connect_role"] = "worker"
    payload["explanation"] = "Connected as worker; the chief will assign work based on session backlog and capabilities."
    return payload


def coordinate_from_args(args: argparse.Namespace) -> dict[str, Any]:
    connect_payload = connect_from_args(
        argparse.Namespace(
            command="connect",
            config=getattr(args, "config", None),
            agent=getattr(args, "agent", None),
            hub_http=getattr(args, "hub_http", None),
            hub_ws=getattr(args, "hub_ws", None),
            workspace=getattr(args, "workspace", None),
            managed_workspace=getattr(args, "managed_workspace", None),
            agent_token=getattr(args, "agent_token", None),
            session_id=getattr(args, "session_id", None),
            project=getattr(args, "project", None),
            role=getattr(args, "role", "worker"),
            capabilities=getattr(args, "capabilities", None),
            provider=getattr(args, "provider", None),
            wait_for_session=getattr(args, "wait_for_session", 120.0),
            prefer_latest=getattr(args, "prefer_latest", False),
            skip_ready=getattr(args, "skip_ready", False),
            start_runner=False,
            start_chief=False,
            backlog_dir=None,
            wait_timeout_seconds=getattr(args, "listen_timeout_seconds", DEFAULT_LISTEN_TIMEOUT_SECONDS),
            task_timeout_seconds=1800.0,
            retry_delay_seconds=getattr(args, "retry_delay_seconds", 2.0),
        )
    )

    connect_role = str(connect_payload.get("connect_role") or "worker").strip().lower()
    if connect_role == "chief":
        return {
            "status": connect_payload.get("status", "connected"),
            "coordinate_role": "chief",
            "connect": connect_payload,
            "next_command": connect_payload.get("chief_command"),
            "explanation": "Chief coordination is long-running; start the returned chief command instead of waiting for one worker turn.",
        }

    config_path_value = connect_payload.get("config_path") or getattr(args, "config", None)
    if not isinstance(config_path_value, str) or not config_path_value.strip():
        raise ValueError("coordinate could not resolve a config_path after connect.")

    listen_args = _listen_namespace_for_config(Path(config_path_value), stop_after_message=True)
    listen_args.timeout_seconds = float(getattr(args, "listen_timeout_seconds", DEFAULT_LISTEN_TIMEOUT_SECONDS))
    listen_args.retry_delay_seconds = float(getattr(args, "retry_delay_seconds", 2.0))
    listen_args.emit = False
    message_payload = listen_for_session_message(listen_args)

    return {
        "status": "message_received",
        "coordinate_role": "worker",
        "connect": connect_payload,
        "message": message_payload,
        "reply_command_hint": f"python {ACP_ROOT / 'acp.py'} reply --config {config_path_value} --to <sender> --payload-file <path>",
    }


def invite_from_args(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    settings: HubAgentSettings | None = None
    try:
        settings = resolve_hub_agent_settings(args, require_hub_http=False)
        config = settings.config
    except Exception:
        settings = None
    role = str(getattr(args, "role", "worker") or "worker").strip().lower()
    capabilities = capabilities_from_args_config(args, config)
    agent_name = getattr(args, "agent", None) or ("worker-1" if role == "worker" else "codex-chief")
    project = getattr(args, "project", None) or get_config_value(config, "project") or "PROJECT_ID"
    workspace = getattr(args, "workspace", None) or "/path/to/project"
    session_id = getattr(args, "session_id", None) or get_config_value(config, "session_id") or "SESSION_ID"
    hub_http = getattr(args, "hub_http", None) or (settings.hub_http if settings is not None else None) or _default_hub_http() or "https://HOST"
    capability_arg = f" --capabilities {','.join(capabilities)}" if capabilities else ""
    if role == "chief":
        command = (
            f"python ACP_AGENT/acp.py connect --role chief --agent {agent_name} "
            f"--agent-token <MANAGED_TOKEN> --project {project} --workspace {workspace}{capability_arg}"
        )
        body = (
            f"Sos el chief de ACP para el proyecto {project}. Conectate al hub {hub_http}, "
            "crea o retoma la sala managed y coordiná el backlog con `chief start`.\n\n"
            f"Comando:\n{command}"
        )
    else:
        command = (
            f"python ACP_AGENT/acp.py connect --role worker --agent {agent_name} "
            f"--agent-token <MANAGED_TOKEN> --session-id {session_id} --project {project} "
            f"--workspace {workspace}{capability_arg}"
        )
        body = (
            f"Sos un worker ACP para el proyecto {project}. Conectate, publicá tus capacidades "
            "y quedate a disposición del chief; no inventes tareas, esperá TASKs.\n\n"
            f"Comando:\n{command}"
        )
    return {
        "status": "ok",
        "role": role,
        "agent_name": agent_name,
        "capabilities": capabilities,
        "session_id": session_id if role == "worker" else None,
        "hub_http": hub_http,
        "command": command,
        "prompt": body,
    }


def _no_session_orientation_hint() -> str:
    return (
        "No ACP session is bound to this config yet. "
        "If this agent is a worker, run `python ACP_AGENT/acp.py connect --role worker --agent-token <MANAGED_TOKEN>`. "
        "If this agent is the workspace chief, run `python ACP_AGENT/acp.py connect --role chief --agent-token <MANAGED_TOKEN>` "
        "or bind an existing config first. If the ACP skill is not installed globally, run `python ACP_AGENT/acp.py onboard-help`."
    )


def _with_orientation_hint(message: str) -> str:
    lower = message.lower()
    if "session_id and member_token are required" in lower or "create or join a session first" in lower:
        return f"{message}\n\n{_no_session_orientation_hint()}"
    return message


def onboard_help_from_args(args: argparse.Namespace) -> dict[str, Any]:
    tool_path = (ACP_ROOT / "acp.py").resolve()
    skill_path = (ACP_ROOT / "skills" / "acp-session-coordinator" / "SKILL.md").resolve()
    agent_name = getattr(args, "agent", None) or "AGENT_NAME"
    project = getattr(args, "project", None) or "PROJECT_ID"
    hub_http = getattr(args, "hub_http", None) or _default_hub_http() or "https://HOST"
    worker_command = (
        f"python {tool_path} connect --role worker --agent {agent_name} "
        f"--agent-token <MANAGED_TOKEN> --project {project} --workspace /path/to/project"
    )
    chief_command = (
        f"python {tool_path} connect --role chief --agent {agent_name} "
        f"--agent-token <MANAGED_TOKEN> --project {project} --workspace /path/to/project"
    )
    text = (
        "ACP quickstart: the executable client is acp.py in this bundle; the skill is optional documentation.\n"
        f"Tool: {tool_path}\n"
        f"Bundled skill: {skill_path}\n"
        f"Hub: {hub_http}\n"
        "Intercom: ACP itself via managed sessions, send/wait/listen; no extra broker is required.\n"
        f"Worker connect: {worker_command}\n"
        f"Chief connect: {chief_command}"
    )
    return {
        "status": "ok",
        "tool_path": str(tool_path),
        "bundled_skill_path": str(skill_path),
        "skill_required": False,
        "hub_http": hub_http,
        "worker_command": worker_command,
        "chief_command": chief_command,
        "text": text,
    }


def managed_close_from_args(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, config = managed_command_hub_http_from_args(args, command_name="managed-close")
    workspace_slug = _managed_workspace_slug_arg(args)
    agent_token = managed_agent_token_from_args(args, config)
    session_id = str(args.session_id).strip()
    if not session_id:
        raise ValueError("session_id is required.")
    managed_close_suffix = f"/sessions/{urllib.parse.quote(session_id, safe='')}/close"
    response = request_json(
        method="POST",
        url=f"{hub_http.rstrip('/')}{_managed_agent_route(workspace_slug=workspace_slug, suffix=managed_close_suffix)}",
        payload={"detail": args.detail},
        headers=_managed_agent_headers(agent_token),
        timeout_seconds=30.0,
    )
    if response.get("workspace") is not None:
        response["managed_workspace_slug"] = response["workspace"].get("slug") if isinstance(response["workspace"], dict) else None
    response["managed_command"] = "managed-close"
    return response


def attach_session_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = ensure_detached_session_bootstrap(
        resolve_hub_agent_settings(args),
        command_name="attach-session",
    )
    session_id = str(args.session_id).strip()
    member_token = str(args.member_token).strip()
    if not session_id:
        raise ValueError("session_id is required.")
    if not member_token:
        raise ValueError("member_token is required.")
    join_code = str(args.join_code).strip() if isinstance(args.join_code, str) and args.join_code.strip() else None
    member_role = str(args.member_role).strip() if isinstance(args.member_role, str) and args.member_role.strip() else None
    operational_settings = _persist_session_binding(
        settings=settings,
        session_id=session_id,
        member_token=member_token,
        join_code=join_code,
        member_role=member_role,
        dashboard_session_path=settings.dashboard_session_path,
        hub_ws_override=getattr(args, "hub_ws", None) or settings.hub_ws or _derive_hub_ws_from_http(settings.hub_http),
    )
    payload: dict[str, Any] = {
        "status": "attached",
        "session_id": session_id,
        "member_token": member_token,
        "member_role": member_role,
        "join_code": join_code,
        "managed_command": "attach-session",
    }
    return enrich_session_payload(
        settings=operational_settings,
        payload=payload,
        session_id=session_id,
        member_token=member_token,
        join_code=join_code,
        member_role=member_role,
    )


def attach_session_and_optionally_listen(args: argparse.Namespace, *, listen_after: bool) -> dict[str, Any]:
    payload = attach_session_from_args(args)
    emit_json_line(payload)
    config_path = resolve_cli_config_path(
        config_path=getattr(args, "config", None),
        agent_name=getattr(args, "agent", None),
        command_name=getattr(args, "command", "attach-session"),
    )
    maybe_start_listen_after_session(
        config_path=config_path,
        mode="persistent" if listen_after else "none",
        command_name=getattr(args, "command", "attach-session"),
    )
    return payload


def wait_for_session_message(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    response = post_json(
        hub_http=settings.hub_http,
        route="/sessions/wait",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "timeout_seconds": float(args.timeout_seconds),
        },
        token=settings.token,
    )
    if response.get("status") == "message":
        apply_session_notice_if_needed(
            settings=settings,
            message=response.get("message") if isinstance(response.get("message"), dict) else None,
            target_payload=response,
        )
    return response


def cancel_session_wait(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/cancel-wait",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
        },
        token=settings.token,
    )


def wait_window_for_session_message(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")

    window_minutes = float(args.window_minutes)
    if window_minutes <= 0:
        raise ValueError("window_minutes must be > 0.")

    per_request_timeout = float(args.timeout_seconds)
    if per_request_timeout <= 0:
        raise ValueError("timeout_seconds must be > 0.")
    per_request_timeout = min(per_request_timeout, 300.0)
    auto_busy_window = max(float(getattr(args, "auto_busy_heartbeat_minutes", 0.0) or 0.0), 0.0)
    auto_busy_interval = float(getattr(args, "auto_busy_heartbeat_interval_seconds", 45.0) or 45.0)
    if auto_busy_interval <= 0:
        raise ValueError("auto_busy_heartbeat_interval_seconds must be > 0.")

    deadline = time.monotonic() + (window_minutes * 60.0)
    inbox_dir = resolve_agent_queue_dir(settings, "inbox_dir", "inbox", fallback=f"inbox/{settings.agent_name}")
    ensure_queue_dirs(inbox_dir)
    safe_update_session_status(settings=settings, state="waiting", text="waiting for session activity")

    while time.monotonic() < deadline:
        remaining = max(deadline - time.monotonic(), 0.0)
        if remaining <= 0:
            break
        current_timeout = min(per_request_timeout, remaining, 300.0)
        response = post_json(
            hub_http=settings.hub_http,
            route="/sessions/wait",
            payload={
                "session_id": settings.session_id,
                "agent_name": settings.agent_name,
                "member_token": settings.member_token,
                "timeout_seconds": current_timeout,
            },
            token=settings.token,
        )
        if response.get("status") == "timeout":
            continue
        if response.get("status") == "message":
            enriched = dict(response)
            enriched["listener_mode"] = "window"
            enriched["window_minutes"] = window_minutes
            message = enriched.get("message")
            if isinstance(message, dict):
                local_inbox_path = append_inbound_message(inbox_dir, message)
                enriched["local_inbox_path"] = str(local_inbox_path)
                notice = apply_session_notice_if_needed(
                    settings=settings,
                    message=message,
                    target_payload=enriched,
                )
                auto_busy = maybe_start_auto_busy_hold(
                    settings=settings,
                    message=message,
                    default_window_minutes=auto_busy_window,
                    interval_seconds=auto_busy_interval,
                )
                if auto_busy is not None:
                    enriched["auto_busy_hold"] = auto_busy
                if notice is not None:
                    return enriched
            return enriched
        return response

    return {
        "status": "timeout",
        "listener_mode": "window",
        "window_minutes": window_minutes,
        "window_closed_at": utc_now_rfc3339(),
    }


def safe_update_session_status(*, settings: HubAgentSettings, state: str, text: str | None) -> None:
    if settings.session_id is None or settings.member_token is None:
        return
    payload = {
        "session_id": settings.session_id,
        "agent_name": settings.agent_name,
        "member_token": settings.member_token,
        "status": state,
        "status_text": text,
    }
    capabilities = optional_capabilities_from_args_config(argparse.Namespace(), settings.config)
    if capabilities is not None:
        payload["capabilities"] = capabilities
    try:
        post_json(
            hub_http=settings.hub_http,
            route="/sessions/status",
            payload=payload,
            token=settings.token,
        )
    except Exception:
        return


def session_notice_details(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    if str(message.get("from") or "").lower() != "system":
        return None
    system_event = str(message.get("system_event") or "").upper()
    if system_event not in {"SESSION_CLOSED", "MEMBER_DISCONNECTED", "MEMBER_LEFT"}:
        return None
    return {
        "system_event": system_event,
        "session_closed": bool(message.get("session_closed")),
        "forced": bool(message.get("forced")),
        "payload": str(message.get("payload") or "").strip(),
        "removed_by": message.get("removed_by"),
        "removed_agent": message.get("removed_agent"),
    }


def apply_session_notice_if_needed(
    *,
    settings: HubAgentSettings,
    message: dict[str, Any] | None,
    target_payload: dict[str, Any],
) -> dict[str, Any] | None:
    notice = session_notice_details(message)
    if notice is None:
        return None
    clear_session_credentials(settings.config_path, settings.config)
    target_payload["session_notice"] = notice
    target_payload["session_credentials_cleared"] = True
    return notice


def _is_fatal_session_command_error(message: str) -> bool:
    return any(
        marker in message
        for marker in (
            "hub HTTP 400:",
            "hub HTTP 401:",
            "hub HTTP 403:",
            "hub HTTP 404:",
            "hub HTTP 409:",
            "session_id and member_token are required",
        )
    )


def _heartbeat_payload(*, settings: HubAgentSettings, detail: str | None) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    payload = {
        "session_id": settings.session_id,
        "agent_name": settings.agent_name,
        "member_token": settings.member_token,
        "detail": detail,
    }
    capabilities = optional_capabilities_from_args_config(argparse.Namespace(), settings.config)
    if capabilities is not None:
        payload["capabilities"] = capabilities
    return payload


def _hold_status_with_heartbeats(
    *,
    settings: HubAgentSettings,
    state: str,
    text: str | None,
    window_minutes: float,
    interval_seconds: float,
    initial_payload: dict[str, Any],
) -> dict[str, Any]:
    if window_minutes <= 0:
        return initial_payload
    if state not in {"busy", "waiting"}:
        raise ValueError("heartbeat window is supported only for busy or waiting status.")
    if interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be > 0.")

    deadline = time.monotonic() + (window_minutes * 60.0)
    heartbeat_count = 0
    heartbeat_failures = 0
    last_member = initial_payload.get("member")

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_seconds, remaining))
        if time.monotonic() >= deadline:
            break
        try:
            response = post_json(
                hub_http=settings.hub_http,
                route="/sessions/heartbeat",
                payload=_heartbeat_payload(settings=settings, detail=text),
                token=settings.token,
            )
        except ValueError as exc:
            if _is_fatal_session_command_error(str(exc)):
                raise
            heartbeat_failures += 1
            continue
        except Exception:
            heartbeat_failures += 1
            continue
        heartbeat_count += 1
        if isinstance(response.get("member"), dict):
            last_member = response["member"]

    result = dict(initial_payload)
    result["heartbeat_window_minutes"] = window_minutes
    result["heartbeat_interval_seconds"] = interval_seconds
    result["heartbeat_count"] = heartbeat_count
    result["heartbeat_failures"] = heartbeat_failures
    if isinstance(last_member, dict):
        result["member"] = last_member
    return result


def _extract_marked_busy_hold(payload_text: Any, *, default_window_minutes: float) -> dict[str, Any] | None:
    if not isinstance(payload_text, str):
        return None
    candidate_text = payload_text
    try:
        parsed = json.loads(payload_text)
    except (ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("instructions"), str):
        candidate_text = parsed["instructions"]
    match = _LONG_TASK_MARKER.match(candidate_text)
    if match is None:
        return None
    raw_minutes = match.group("minutes")
    if raw_minutes is not None:
        try:
            minutes = float(raw_minutes)
        except ValueError:
            return None
        if minutes <= 0:
            return None
    else:
        if default_window_minutes <= 0:
            return None
        minutes = default_window_minutes
    detail = candidate_text[match.end():].strip() or "processing long task"
    return {
        "window_minutes": minutes,
        "detail": detail,
        "marker": match.group(0).strip(),
    }


# --- Local embedded Hub lifecycle ---
#
# ACP_AGENT is portable and only depends on websockets; the real Hub (apps/hub)
# is a separate FastAPI package. Local mode auto-launches that real Hub on
# 127.0.0.1 as a background process and reuses it across CLI invocations, so a
# developer can coordinate locally with no remote infra while speaking the exact
# same protocol that scales to a remote Hub.

LOCAL_HUB_DEFAULT_HOST = "127.0.0.1"
LOCAL_HUB_DEFAULT_PORT = 8000


def local_hub_state_path() -> Path:
    return ACP_ROOT / ".local_hub.json"


def read_local_hub_state() -> dict[str, Any] | None:
    path = local_hub_state_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_local_hub_state(state: dict[str, Any]) -> Path:
    path = local_hub_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, state)
    return path


def clear_local_hub_state() -> None:
    try:
        local_hub_state_path().unlink()
    except FileNotFoundError:
        pass


def local_hub_sqlite_path() -> Path:
    return ACP_ROOT / ".local_hub" / "acp.sqlite3"


def build_local_hub_command(*, host: str, port: int, python_executable: str | None = None) -> list[str]:
    return [
        python_executable or sys.executable,
        "-m",
        "uvicorn",
        "acp.hub.app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def build_local_hub_env(*, sqlite_path: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    env["ACP_PERSISTENCE_BACKEND"] = "sqlite"
    env["ACP_SQLITE_PATH"] = sqlite_path
    return env


def local_hub_dependencies_available() -> bool:
    import importlib.metadata
    import importlib.util

    # NOTE: ACP_AGENT/acp.py is itself a top-level module named "acp", so an
    # in-process find_spec("acp.hub.app") is shadowed by this script when the
    # ACP_AGENT dir is on sys.path. Check the installed distribution metadata
    # instead, which is immune to the import-name shadow. uvicorn is unrelated
    # to the shadow, so a normal find_spec is fine.
    try:
        if importlib.util.find_spec("uvicorn") is None:
            return False
    except (ImportError, ValueError):
        return False
    try:
        importlib.metadata.distribution("acp-hub")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def local_hub_health_ok(hub_http: str, *, timeout_seconds: float = 1.0) -> bool:
    if not isinstance(hub_http, str) or not hub_http.strip():
        return False
    url = f"{hub_http.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body).get("status") == "ok"
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False


def resolve_local_hub_http() -> str | None:
    state = read_local_hub_state()
    if not state:
        return None
    hub_http = state.get("hub_http")
    if isinstance(hub_http, str) and hub_http.strip() and local_hub_health_ok(hub_http):
        return hub_http.strip()
    return None


def _spawn_local_hub_process(command: list[str], env: dict[str, str]) -> subprocess.Popen:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Launch from a neutral cwd so `python -m uvicorn acp.hub.app:app` resolves
    # `acp` to the installed acp-hub package, not a shadowing acp.py in the
    # caller's directory (the ACP_AGENT folder ships an acp.py module).
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
        env=env,
        cwd=tempfile.gettempdir(),
    )


def _terminate_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError):
        return False


def ensure_local_hub_running(
    *,
    host: str = LOCAL_HUB_DEFAULT_HOST,
    port: int = LOCAL_HUB_DEFAULT_PORT,
    startup_timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.3,
) -> dict[str, Any]:
    existing = read_local_hub_state()
    if existing and local_hub_health_ok(str(existing.get("hub_http", ""))):
        return {"status": "already_running", **existing}

    hub_http = f"http://{host}:{port}"
    if local_hub_health_ok(hub_http):
        adopted = {"hub_http": hub_http, "host": host, "port": port, "pid": None, "adopted": True}
        write_local_hub_state(adopted)
        return {"status": "already_running", **adopted}

    if not local_hub_dependencies_available():
        raise ValueError(
            "Local hub requires the hub package. Install it with: python -m pip install -e apps/hub"
        )

    sqlite_path = local_hub_sqlite_path()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_local_hub_command(host=host, port=port)
    env = build_local_hub_env(sqlite_path=str(sqlite_path))
    process = _spawn_local_hub_process(command, env)

    deadline = time.monotonic() + max(startup_timeout_seconds, 0.1)
    while time.monotonic() < deadline:
        if local_hub_health_ok(hub_http):
            state = {"hub_http": hub_http, "host": host, "port": port, "pid": process.pid}
            write_local_hub_state(state)
            return {"status": "started", **state}
        if process.poll() is not None:
            raise ValueError(
                f"Local hub exited early (code {process.returncode}). "
                "Confirm 'apps/hub' is installed: python -m pip install -e apps/hub"
            )
        time.sleep(poll_interval_seconds)

    raise ValueError(f"Local hub at {hub_http} did not become healthy within {startup_timeout_seconds}s.")


def stop_local_hub() -> dict[str, Any]:
    state = read_local_hub_state()
    if state is None:
        return {"status": "not_running"}
    pid = state.get("pid")
    terminated = False
    if isinstance(pid, int):
        terminated = _terminate_pid(pid)
    clear_local_hub_state()
    return {
        "status": "stopped" if terminated else "cleared",
        "pid": pid,
        "hub_http": state.get("hub_http"),
    }


def local_hub_status() -> dict[str, Any]:
    state = read_local_hub_state()
    if state is None:
        return {"status": "not_running"}
    healthy = local_hub_health_ok(str(state.get("hub_http", "")))
    return {"status": "running" if healthy else "stale", "healthy": healthy, **state}


def quickstart_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """One command to a working local ACP: install skill + deps, provision a
    local-mode agent config, and start a local Hub. Reuses the bundle installer
    so there is a single provisioning code path."""
    import install_from_bundle as installer

    host = getattr(args, "host", LOCAL_HUB_DEFAULT_HOST) or LOCAL_HUB_DEFAULT_HOST
    port = int(getattr(args, "port", LOCAL_HUB_DEFAULT_PORT) or LOCAL_HUB_DEFAULT_PORT)
    hub_http = f"http://{host}:{port}"
    hub_ws = f"ws://{host}:{port}/ws"
    agent_names = list(dict.fromkeys(getattr(args, "agent", None) or []))
    if not agent_names:
        raise ValueError("quickstart requires at least one --agent <name>.")

    dependencies = installer.ensure_runtime_dependencies(
        skip_install=bool(getattr(args, "skip_install_deps", False))
    )

    skill_args = argparse.Namespace(
        skill_home=getattr(args, "skill_home", None),
        claude_skill_home=getattr(args, "claude_skill_home", None),
    )
    skill_paths: list[str] = []
    for skill_home in installer.resolve_skill_homes(skill_args):
        skill_home.mkdir(parents=True, exist_ok=True)
        skill_paths.append(str(installer.install_skill(skill_home=skill_home, force=True)))

    installer.initialize_agent_folder(
        acp_root=ACP_ROOT,
        hub_mode="local",
        hub_http=hub_http,
        hub_ws=hub_ws,
        agent_names=agent_names,
        token=getattr(args, "token", None),
        force=True,
    )
    bundle_info = installer.write_bundle_info(target_root=ACP_ROOT, source="quickstart")

    try:
        hub = ensure_local_hub_running(host=host, port=port)
    except ValueError as exc:
        hub = {"status": "not_started", "detail": str(exc)}

    first_agent = agent_names[0]
    next_steps = [
        f'python ACP_AGENT/acp.py create-session --agent {first_agent} --title "My task"',
        "python ACP_AGENT/acp.py listen --stop-after-message --timeout-seconds 300",
    ]
    if hub.get("status") == "not_started":
        next_steps.insert(0, "python -m pip install -e apps/hub   # then re-run quickstart or: python ACP_AGENT/acp.py hub-up")

    return {
        "status": "ok",
        "mode": "local",
        "hub": hub,
        "hub_http": hub_http,
        "hub_ws": hub_ws,
        "agents": agent_names,
        "configs": [str(ACP_ROOT / "agents" / f"{name}.json") for name in agent_names],
        "skill_paths": skill_paths,
        "dependencies": dependencies,
        "bundle_info": bundle_info,
        "next_steps": next_steps,
    }


def _launch_busy_hold_subprocess(
    *,
    settings: HubAgentSettings,
    detail: str,
    window_minutes: float,
    interval_seconds: float,
) -> dict[str, Any]:
    script_path = Path(__file__).resolve()
    command = [
        sys.executable,
        str(script_path),
        "status",
        "--config",
        str(settings.config_path),
        "--state",
        "busy",
        "--text",
        detail,
        "--heartbeat-window-minutes",
        str(window_minutes),
        "--heartbeat-interval-seconds",
        str(interval_seconds),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    return {
        "status": "started",
        "pid": process.pid,
        "window_minutes": window_minutes,
        "interval_seconds": interval_seconds,
        "detail": detail,
        "command": " ".join(command),
    }


def maybe_start_auto_busy_hold(
    *,
    settings: HubAgentSettings,
    message: dict[str, Any] | None,
    default_window_minutes: float,
    interval_seconds: float,
) -> dict[str, Any] | None:
    if interval_seconds <= 0:
        raise ValueError("auto_busy_heartbeat_interval_seconds must be > 0.")
    if not isinstance(message, dict):
        return None
    if str(message.get("action") or "").upper() != "TASK":
        return None
    marked = _extract_marked_busy_hold(message.get("payload"), default_window_minutes=default_window_minutes)
    if marked is None:
        return None
    try:
        launched = _launch_busy_hold_subprocess(
            settings=settings,
            detail=str(marked["detail"]),
            window_minutes=float(marked["window_minutes"]),
            interval_seconds=interval_seconds,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "window_minutes": float(marked["window_minutes"]),
            "interval_seconds": interval_seconds,
            "detail": str(marked["detail"]),
            "marker": marked["marker"],
            "error": str(exc),
        }
    launched["marker"] = marked["marker"]
    return launched


def listen_for_session_message(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")

    update_result = maybe_handle_idle_update(settings=settings, args=args)
    if update_result is not None:
        emit_json_line({"status": "idle_update_check", "result": update_result})

    timeout_seconds = float(args.timeout_seconds)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0.")

    retry_delay_seconds = max(float(args.retry_delay_seconds), 0.1)
    stop_after_message = bool(getattr(args, "stop_after_message", False))
    auto_busy_window = max(float(getattr(args, "auto_busy_heartbeat_minutes", 0.0) or 0.0), 0.0)
    auto_busy_interval = float(getattr(args, "auto_busy_heartbeat_interval_seconds", 45.0) or 45.0)
    if auto_busy_window > 0 and not stop_after_message:
        raise ValueError("listen auto busy hold requires --stop-after-message.")
    if auto_busy_interval <= 0:
        raise ValueError("auto_busy_heartbeat_interval_seconds must be > 0.")
    last_timeout_at: str | None = None
    inbox_dir = resolve_agent_queue_dir(settings, "inbox_dir", "inbox", fallback=f"inbox/{settings.agent_name}")
    ensure_queue_dirs(inbox_dir)
    safe_update_session_status(settings=settings, state="waiting", text="waiting for session activity")

    while True:
        try:
            response = post_json(
                hub_http=settings.hub_http,
                route="/sessions/wait",
                payload={
                    "session_id": settings.session_id,
                    "agent_name": settings.agent_name,
                    "member_token": settings.member_token,
                    "timeout_seconds": timeout_seconds,
                },
                token=settings.token,
            )
        except ValueError as exc:
            message = str(exc)
            if ("hub HTTP 403:" in message or "hub HTTP 404:" in message) and _is_stale_session_binding_error(message):
                # The Hub no longer recognizes this session/binding: it was
                # closed without a live notice, the member token was rotated, or
                # the Hub redeployed with an in-memory store. Clear the dead
                # local binding and exit cleanly so a turn-based agent re-creates
                # or re-joins instead of looping or surfacing an opaque 403/404.
                try:
                    clear_session_credentials(settings.config_path, settings.config)
                    cleared_local_session = True
                except OSError:
                    cleared_local_session = False
                ended_payload = {
                    "status": "session_ended",
                    "agent_name": settings.agent_name,
                    "session_id": settings.session_id,
                    "detail": message,
                    "cleared_local_session": cleared_local_session,
                    "next_step": "the session no longer exists on the Hub; run create-session or join-session before listening again.",
                }
                emit_json_line(ended_payload)
                return ended_payload
            if any(
                marker in message
                for marker in (
                    "hub HTTP 400:",
                    "hub HTTP 401:",
                    "hub HTTP 403:",
                    "hub HTTP 404:",
                    "hub HTTP 409:",
                    "session_id and member_token are required",
                    "timeout_seconds must be between 0 and 300",
                )
            ):
                raise
            last_timeout_at = utc_now_rfc3339()
            continue_payload = {
                "status": "listener_retry",
                "agent_name": settings.agent_name,
                "session_id": settings.session_id,
                "detail": message,
                "last_retry_at": last_timeout_at,
            }
            emit_json_line(continue_payload)
            time.sleep(retry_delay_seconds)
            continue

        if response.get("status") == "timeout":
            last_timeout_at = utc_now_rfc3339()
            continue
        if response.get("status") == "message":
            enriched = dict(response)
            if last_timeout_at is not None:
                enriched["listener_resumed_after"] = last_timeout_at
            enriched["listener_mode"] = "persistent"
            message = enriched.get("message")
            notice: dict[str, Any] | None = None
            if isinstance(message, dict):
                local_inbox_path = append_inbound_message(inbox_dir, message)
                enriched["local_inbox_path"] = str(local_inbox_path)
                notice = apply_session_notice_if_needed(
                    settings=settings,
                    message=message,
                    target_payload=enriched,
                )
                if stop_after_message:
                    auto_busy = maybe_start_auto_busy_hold(
                        settings=settings,
                        message=message,
                        default_window_minutes=auto_busy_window,
                        interval_seconds=auto_busy_interval,
                    )
                    if auto_busy is not None:
                        enriched["auto_busy_hold"] = auto_busy
            if bool(getattr(args, "emit", True)):
                emit_json_line(enriched)
            if stop_after_message or notice is not None:
                return enriched
            safe_update_session_status(settings=settings, state="waiting", text="waiting for session activity")
            continue
        return response


def update_session_status(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    capabilities = optional_capabilities_from_args_config(args, settings.config)
    if getattr(args, "capabilities", None) is not None:
        updated = dict(settings.config)
        updated["capabilities"] = capabilities
        write_config(settings.config_path, updated)
        settings = derive_hub_agent_settings(settings=settings, config=updated)
    payload = {
        "session_id": settings.session_id,
        "agent_name": settings.agent_name,
        "member_token": settings.member_token,
        "status": args.state,
        "status_text": args.text,
    }
    if capabilities is not None:
        payload["capabilities"] = capabilities
    result = post_json(
        hub_http=settings.hub_http,
        route="/sessions/status",
        payload=payload,
        token=settings.token,
    )
    return _hold_status_with_heartbeats(
        settings=settings,
        state=args.state,
        text=args.text,
        window_minutes=float(getattr(args, "heartbeat_window_minutes", 0.0) or 0.0),
        interval_seconds=float(getattr(args, "heartbeat_interval_seconds", 45.0) or 45.0),
        initial_payload=result,
    )


def heartbeat_session(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if getattr(args, "capabilities", None) is not None:
        updated = dict(settings.config)
        updated["capabilities"] = capabilities_from_args_config(args, settings.config)
        write_config(settings.config_path, updated)
        settings = derive_hub_agent_settings(settings=settings, config=updated)
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/heartbeat",
        payload=_heartbeat_payload(settings=settings, detail=args.text),
        token=settings.token,
    )


def fetch_session_info(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    route = (
        f"/sessions/{settings.session_id}"
        f"?agent_name={urllib.parse.quote(settings.agent_name)}"
        f"&member_token={urllib.parse.quote(settings.member_token)}"
    )
    response = get_json(hub_http=settings.hub_http, route=route, token=settings.token)
    join_code = _session_payload_value(response, "join_code")
    member_role = _resolve_member_role(payload=response, agent_name=settings.agent_name)
    if not isinstance(join_code, str) or not join_code.strip():
        join_code = settings.config.get("join_code")
    if not isinstance(member_role, str) or not member_role.strip():
        member_role = settings.config.get("member_role")
    enriched = enrich_session_payload(
        settings=settings,
        payload=response,
        session_id=settings.session_id,
        member_token=settings.member_token,
        join_code=join_code if isinstance(join_code, str) else None,
        member_role=member_role if isinstance(member_role, str) else None,
    )
    if not bool(getattr(args, "skip_update_check", False)):
        hint = build_release_update_hint(settings=settings, manifest_url=getattr(args, "manifest_url", None))
        if hint is not None:
            enriched["release_update"] = hint
    return enriched


def _resolve_hub_http_simple(args: argparse.Namespace) -> tuple[str, str | None]:
    """Resolve hub_http and optional token without requiring full session credentials.

    Order of resolution:
    1. Explicit --hub-http on the command line.
    2. Config file selected via --config or --agent (no requirement that the
       config already holds session credentials).
    3. Distribution default if the bundle ships one.
    """
    hub_http = getattr(args, "hub_http", None)
    token = getattr(args, "token", None)
    if hub_http is not None and isinstance(hub_http, str) and hub_http.strip():
        return _normalize_hub_http(hub_http), token.strip() if isinstance(token, str) and token.strip() else None

    agent_name = getattr(args, "agent", None) or getattr(args, "name", None)
    config_path_arg = getattr(args, "config", None)
    if config_path_arg or agent_name:
        try:
            config_path = resolve_cli_config_path(
                config_path=config_path_arg,
                agent_name=agent_name,
                command_name=getattr(args, "command", "acp"),
            )
            config, _ = load_config(str(config_path))
            hub_http_from_cfg = _normalize_hub_http(get_config_value(config, "hub_http"))
            if hub_http_from_cfg:
                cfg_token = get_config_value(config, "token") if token is None else token
                if isinstance(cfg_token, str) and cfg_token.strip():
                    return hub_http_from_cfg, cfg_token.strip()
                return hub_http_from_cfg, None
        except (ValueError, OSError):
            pass

    default_hub_http = _default_hub_http()
    if default_hub_http:
        return default_hub_http, token.strip() if isinstance(token, str) and token.strip() else None
    raise ValueError("hub_http is required (via --hub-http, --agent config, or a distribution default)")


def _release_manifest_url(*, hub_http: str | None = None, manifest_url: Any = None) -> str:
    if isinstance(manifest_url, str) and manifest_url.strip():
        return manifest_url.strip()
    distribution_manifest = _distribution().default_manifest_url
    if distribution_manifest:
        return distribution_manifest
    if isinstance(hub_http, str) and hub_http.strip():
        return f"{hub_http.rstrip('/')}/downloads/ACP_AGENT.json"
    raise ValueError("release manifest URL is required (via --manifest-url, config hub_http, or distribution default)")


def _local_update_policy(config: dict[str, Any], override: Any = None) -> str:
    raw_policy = override if isinstance(override, str) and override.strip() else config.get("update_policy")
    policy = str(raw_policy or "off").strip().lower().replace("_", "-")
    if policy in {"auto", "auto-idle", "auto-when-idle"}:
        return "auto-when-idle"
    if policy in {"off", "notify"}:
        return policy
    return "notify"


def check_release_update(*, target_dir: Path = ACP_ROOT, manifest_url: str) -> dict[str, Any]:
    from update_from_release import check_for_update

    comparison = check_for_update(target_dir=target_dir, manifest_url=manifest_url)
    manifest = comparison.get("manifest")
    if isinstance(manifest, dict):
        comparison = dict(comparison)
        comparison["manifest"] = {
            "version": manifest.get("version"),
            "released_at": manifest.get("released_at"),
            "agent_update": manifest.get("agent_update"),
            "update_policy": manifest.get("update_policy"),
        }
    return comparison


def build_release_update_hint(*, settings: HubAgentSettings, manifest_url: Any = None) -> dict[str, Any] | None:
    try:
        resolved_manifest_url = _release_manifest_url(hub_http=settings.hub_http, manifest_url=manifest_url)
        comparison = check_release_update(target_dir=ACP_ROOT, manifest_url=resolved_manifest_url)
    except Exception as exc:
        return {
            "status": "unavailable",
            "detail": str(exc),
        }
    if comparison.get("status") == "current":
        return {
            "status": "current",
            "local_version": comparison.get("local_version"),
            "remote_version": comparison.get("remote_version"),
            "manifest_url": resolved_manifest_url,
        }
    return {
        "status": comparison.get("status"),
        "local_version": comparison.get("local_version"),
        "remote_version": comparison.get("remote_version"),
        "manifest_url": resolved_manifest_url,
        "auto_update": comparison.get("auto_update"),
        "recommended_next_step": (
            "Run python ACP_AGENT/update_from_release.py --auto-when-idle when this ACP_AGENT folder is untracked, "
            "or update manually if ACP_AGENT is tracked by the project repo."
        ),
    }


def maybe_handle_idle_update(*, settings: HubAgentSettings, args: argparse.Namespace) -> dict[str, Any] | None:
    policy = _local_update_policy(settings.config, getattr(args, "update_policy", None))
    if policy == "off":
        return None
    try:
        manifest_url = _release_manifest_url(hub_http=settings.hub_http, manifest_url=getattr(args, "manifest_url", None))
        comparison = check_release_update(target_dir=ACP_ROOT, manifest_url=manifest_url)
    except Exception as exc:
        if policy == "auto-when-idle":
            return {"status": "update_check_unavailable", "detail": str(exc)}
        return None
    if comparison.get("status") == "current":
        return None
    if policy == "notify":
        return {
            "status": "update_available",
            "local_version": comparison.get("local_version"),
            "remote_version": comparison.get("remote_version"),
            "manifest_url": manifest_url,
            "auto_update": comparison.get("auto_update"),
        }

    from update_from_release import update_from_manifest

    result = update_from_manifest(
        target_dir=ACP_ROOT,
        manifest_url=manifest_url,
        force=False,
        auto_when_idle=True,
        allow_tracked_repo=bool(getattr(args, "allow_tracked_auto_update", False)),
    )
    result["manifest_url"] = manifest_url
    return result


def cmd_update_check(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, _token = _resolve_hub_http_simple(args)
    manifest_url = _release_manifest_url(hub_http=hub_http, manifest_url=getattr(args, "manifest_url", None))
    payload = check_release_update(target_dir=ACP_ROOT, manifest_url=manifest_url)
    payload["manifest_url"] = manifest_url
    return payload


def cmd_self_update(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, _token = _resolve_hub_http_simple(args)
    manifest_url = _release_manifest_url(hub_http=hub_http, manifest_url=getattr(args, "manifest_url", None))
    from update_from_release import update_from_manifest

    payload = update_from_manifest(
        target_dir=ACP_ROOT,
        manifest_url=manifest_url,
        force=bool(getattr(args, "force", False)),
        auto_when_idle=bool(getattr(args, "auto_when_idle", False)),
        allow_tracked_repo=bool(getattr(args, "allow_tracked_repo", False)),
    )
    payload["manifest_url"] = manifest_url
    return payload


def cmd_health(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, token = _resolve_hub_http_simple(args)
    payload = get_json(hub_http=hub_http, route="/health", token=token)
    return {"hub_http": hub_http, "health": payload}


def cmd_agents(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, token = _resolve_hub_http_simple(args)
    payload = get_json(hub_http=hub_http, route="/agents", token=token)
    return {"hub_http": hub_http, "agents": payload}


def cmd_overview(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, token = _resolve_hub_http_simple(args)
    if token is None:
        raise ValueError("/dashboard/overview requires an admin token (--token or config.token)")
    payload = get_json(hub_http=hub_http, route="/dashboard/overview", token=token)
    return {"hub_http": hub_http, "overview": payload}


def cmd_sessions(args: argparse.Namespace) -> dict[str, Any]:
    """List sessions from the global overview, filtered to active by default."""
    hub_http, token = _resolve_hub_http_simple(args)
    if token is None:
        raise ValueError("listing sessions requires an admin token (--token or config.token)")
    payload = get_json(hub_http=hub_http, route="/dashboard/overview", token=token)
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, list):
        sessions = []
    only_active = bool(getattr(args, "active", False))
    if only_active:
        sessions = [
            s for s in sessions
            if isinstance(s, dict) and str(s.get("status", "")).lower() in {"open", "active", ""}
        ]
    return {"hub_http": hub_http, "sessions": sessions, "count": len(sessions)}


def cmd_replay(args: argparse.Namespace) -> dict[str, Any]:
    hub_http, token = _resolve_hub_http_simple(args)
    config: dict[str, Any] = {}
    if getattr(args, "config", None) or getattr(args, "agent", None):
        try:
            config_path = resolve_cli_config_path(
                config_path=getattr(args, "config", None),
                agent_name=getattr(args, "agent", None),
                command_name="replay",
            )
            config, _ = load_config(str(config_path))
        except (ValueError, OSError):
            config = {}
    managed_token = getattr(args, "agent_token", None)
    if not (isinstance(managed_token, str) and managed_token.strip()):
        managed_token = get_config_value(config, "managed_agent_token", "agent_token")
    session_id = getattr(args, "session_id", None)
    if not (isinstance(session_id, str) and session_id.strip()):
        session_id = get_config_value(config, "session_id")
    if token is None and isinstance(managed_token, str) and managed_token.strip() and isinstance(session_id, str) and session_id.strip():
        query: list[tuple[str, str]] = []
        for key in ("actor", "action", "event_type", "order", "limit"):
            value = getattr(args, key, None)
            if value is not None and str(value).strip():
                query.append((key, str(value).strip()))
        suffix = ("?" + urllib.parse.urlencode(query)) if query else ""
        payload = request_json(
            method="GET",
            url=f"{hub_http.rstrip('/')}/managed/agent/sessions/{urllib.parse.quote(session_id.strip(), safe='')}/replay{suffix}",
            headers=_managed_agent_headers(managed_token.strip()),
            timeout_seconds=30.0,
            retry_transient=True,
        )
        return {"hub_http": hub_http, "managed": True, "session_id": session_id.strip(), "replay": payload}
    if token is None:
        raise ValueError(
            "replay requires either an admin token (--token or config.token) or managed credentials "
            "(--agent-token/config.managed_agent_token plus --session-id/config.session_id)"
        )
    query: list[tuple[str, str]] = []
    for key in ("from_ts", "to_ts", "actor", "event_type", "message_id", "thread_id", "order", "limit", "cursor"):
        value = getattr(args, key, None)
        if value is not None and str(value).strip():
            query.append((key.replace("from_ts", "from").replace("to_ts", "to"), str(value).strip()))
    suffix = ("?" + urllib.parse.urlencode(query)) if query else ""
    payload = get_json(hub_http=hub_http, route=f"/replay/events{suffix}", token=token)
    return {"hub_http": hub_http, "replay": payload}


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    """End-to-end diagnostics for an ACP_AGENT install.

    Each check has status: "ok", "warn", or "fail". Non-blocking warnings don't
    cause a non-zero exit; only failures do. The result is shaped to be both
    human-readable when pretty-printed and machine-parseable.
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    def add(name: str, status: str, detail: str = "", **extra: Any) -> None:
        nonlocal overall_ok
        entry: dict[str, Any] = {"name": name, "status": status}
        if detail:
            entry["detail"] = detail
        entry.update(extra)
        if status == "fail":
            overall_ok = False
        checks.append(entry)

    # 1. Bundle metadata
    version_file = ACP_ROOT / "VERSION"
    if version_file.exists():
        add("bundle_version", "ok", version_file.read_text(encoding="utf-8").strip())
    else:
        add("bundle_version", "warn", "VERSION file missing; bundle may be incomplete")

    # 2. Distribution
    dist = _distribution()
    add(
        "distribution",
        "ok",
        f"{dist.distribution_id} ({dist.default_hub_mode})",
        default_hub_http=dist.default_hub_http,
    )

    # 3. Resolve hub_http
    try:
        hub_http, token = _resolve_hub_http_simple(args)
        add("hub_http_resolved", "ok", hub_http, has_token=bool(token))
    except ValueError as exc:
        add("hub_http_resolved", "fail", str(exc))
        return {"status": "fail" if not overall_ok else "ok", "checks": checks}

    # 4. /health
    try:
        get_json(hub_http=hub_http, route="/health", token=None)
        add("hub_health", "ok", f"{hub_http}/health responded")
    except (ValueError, urllib.error.URLError, OSError) as exc:
        add("hub_health", "fail", str(exc))

    # 5. /agents (token-gated when ACP_TOKEN is set on the hub)
    try:
        get_json(hub_http=hub_http, route="/agents", token=token)
        add("hub_agents", "ok", "agents endpoint reachable")
    except ValueError as exc:
        # If 401/403 with token unset, treat as warning, not fail
        msg = str(exc)
        if "401" in msg or "403" in msg:
            add("hub_agents", "warn", "agents endpoint requires a valid admin token")
        else:
            add("hub_agents", "fail", msg)
    except (urllib.error.URLError, OSError) as exc:
        add("hub_agents", "fail", str(exc))

    # 6. WebSocket reachable (best-effort: derive ws url and try opening)
    ws_url = _derive_hub_ws_from_http(hub_http)
    if ws_url:
        add("hub_ws_url", "ok", ws_url)
    else:
        add("hub_ws_url", "warn", "could not derive ws URL from hub_http")

    # 7. Agent configs present
    agents_dir = ACP_ROOT / "agents"
    if agents_dir.is_dir():
        configs = sorted(p.name for p in agents_dir.glob("*.json"))
        if configs:
            add("agent_configs", "ok", ", ".join(configs), count=len(configs))
        else:
            add("agent_configs", "warn", "no agent configs under ACP_AGENT/agents/")
    else:
        add("agent_configs", "warn", "ACP_AGENT/agents/ directory missing; run `acp.py init`")

    # 8. .gitignore protection
    gi = ACP_ROOT / ".gitignore"
    if gi.exists():
        content = gi.read_text(encoding="utf-8")
        if "agents/" in content and ("inbox/" in content or "ACP_AGENT/inbox" in content):
            add("local_gitignore", "ok", "tokens and queues are git-ignored locally")
        else:
            add("local_gitignore", "warn", "local .gitignore is missing recommended patterns")
    else:
        add("local_gitignore", "warn", "ACP_AGENT/.gitignore is missing; tokens may leak to git")

    # 9. websockets dependency
    try:
        import websockets  # noqa: F401
        add("websockets_dep", "ok", "websockets module importable")
    except ImportError:
        add("websockets_dep", "fail", "websockets is not installed (pip install -r ACP_AGENT/requirements.txt)")

    return {
        "status": "ok" if overall_ok else "fail",
        "hub_http": hub_http,
        "checks": checks,
    }


def leave_session_from_args(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    response = post_json(
        hub_http=settings.hub_http,
        route="/sessions/leave",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
        },
        token=settings.token,
    )
    clear_session_credentials(settings.config_path, settings.config)
    return response


def dispatch_send(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args, require_hub_http=False)
    if settings.session_id and settings.member_token and settings.hub_http:
        return post_json(
            hub_http=settings.hub_http,
            route="/sessions/send",
            payload=build_session_send_payload(args, settings),
            token=settings.token,
        )
    raise ValueError(
        "send requires an active session (session_id, member_token, hub_http). "
        "Create or join a session first."
    )


def resolve_runner_profile(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    config = dict(settings.config)
    provider_value = getattr(args, "provider", None) or get_config_value(config, "runner_provider", "provider")
    if not isinstance(provider_value, str) or provider_value.strip() not in {"codex_local", "claude_local"}:
        raise ValueError("runner provider is required and must be codex_local or claude_local.")
    workspace_value = getattr(args, "workspace", None) or get_config_value(config, "runner_workspace", "workspace_path")
    workspace_path = normalize_workspace_path(
        resolve_config_path(settings.base_dir, workspace_value) if workspace_value is not None else settings.base_dir
    )
    wait_timeout_seconds = float(
        getattr(args, "wait_timeout_seconds", None)
        or get_config_value(config, "runner_wait_timeout_seconds")
        or 120.0
    )
    if wait_timeout_seconds <= 0 or wait_timeout_seconds > 300:
        raise ValueError("runner wait timeout must be between 0 and 300 seconds.")
    task_timeout_seconds = float(
        getattr(args, "task_timeout_seconds", None)
        or get_config_value(config, "runner_task_timeout_seconds")
        or 1800.0
    )
    if task_timeout_seconds <= 0:
        raise ValueError("runner task timeout must be > 0.")
    retry_delay_seconds = float(getattr(args, "retry_delay_seconds", None) or 2.0)
    raw_auto_busy_minutes = (
        getattr(args, "auto_busy_heartbeat_minutes", None)
        if getattr(args, "auto_busy_heartbeat_minutes", None) is not None
        else get_config_value(config, "runner_auto_busy_heartbeat_minutes")
    )
    auto_busy_minutes = float(raw_auto_busy_minutes if raw_auto_busy_minutes is not None else 30.0)
    raw_auto_busy_interval = (
        getattr(args, "auto_busy_heartbeat_interval_seconds", None)
        if getattr(args, "auto_busy_heartbeat_interval_seconds", None) is not None
        else get_config_value(config, "runner_auto_busy_heartbeat_interval_seconds")
    )
    auto_busy_interval = float(raw_auto_busy_interval if raw_auto_busy_interval is not None else 45.0)
    if auto_busy_minutes < 0:
        raise ValueError("runner auto busy heartbeat minutes must be >= 0.")
    if auto_busy_interval <= 0:
        raise ValueError("runner auto busy heartbeat interval seconds must be > 0.")
    state_path = resolve_config_path(settings.base_dir, get_config_value(config, "runner_state_path"))
    if state_path is None:
        state_path = (settings.base_dir / ".acp_runner_state.json").resolve()
    return {
        "settings": settings,
        "provider": provider_value.strip(),
        "workspace_path": workspace_path,
        "capabilities": optional_capabilities_from_args_config(args, config),
        "wait_timeout_seconds": wait_timeout_seconds,
        "task_timeout_seconds": task_timeout_seconds,
        "retry_delay_seconds": max(retry_delay_seconds, 0.1),
        "auto_busy_heartbeat_minutes": auto_busy_minutes,
        "auto_busy_heartbeat_interval_seconds": auto_busy_interval,
        "state_path": state_path,
    }


def _runner_member_payload(*, profile: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "delivery_mode": "runner",
        "provider": profile["provider"],
        "workspace_path": profile["workspace_path"],
    }
    if profile.get("capabilities") is not None:
        payload["capabilities"] = profile["capabilities"]
    return payload


def bootstrap_runner_session(args: argparse.Namespace, *, command_name: str) -> dict[str, Any]:
    profile = resolve_runner_profile(args)
    settings: HubAgentSettings = profile["settings"]
    updated = dict(settings.config)
    updated["agent_name"] = settings.agent_name
    updated["hub_http"] = settings.hub_http
    if settings.hub_ws:
        updated["hub_ws"] = settings.hub_ws
    updated["hub_mode"] = _hub_mode_for_http(settings.hub_http)
    updated["delivery_mode"] = "runner"
    updated["runner_provider"] = profile["provider"]
    updated["runner_workspace"] = profile["workspace_path"]
    updated["workspace_path"] = profile["workspace_path"]
    if profile["capabilities"] is not None:
        updated["capabilities"] = profile["capabilities"]
    updated["runner_wait_timeout_seconds"] = profile["wait_timeout_seconds"]
    updated["runner_task_timeout_seconds"] = profile["task_timeout_seconds"]
    updated["runner_auto_busy_heartbeat_minutes"] = profile["auto_busy_heartbeat_minutes"]
    updated["runner_auto_busy_heartbeat_interval_seconds"] = profile["auto_busy_heartbeat_interval_seconds"]
    updated.setdefault("runner_state_path", str(profile["state_path"]))

    if getattr(args, "join_code", None):
        settings = ensure_detached_session_bootstrap(settings, command_name=command_name)
        response = post_json(
            hub_http=settings.hub_http,
            route="/sessions/join",
            payload={
                "agent_name": settings.agent_name,
                "join_code": getattr(args, "join_code"),
                "token": settings.token,
                **_runner_member_payload(profile=profile),
            },
            token=settings.token,
        )
        updated["session_id"] = response["session_id"]
        updated["member_token"] = response["member_token"]
        updated["member_role"] = response["member_role"]
        updated["join_code"] = response["join_code"]
        write_config(settings.config_path, updated)
        profile["settings"] = derive_hub_agent_settings(settings=settings, config=updated)
        return profile

    restore_session_id = getattr(args, "session_id", None)
    restore_member_token = getattr(args, "member_token", None)
    if bool(restore_session_id) ^ bool(restore_member_token):
        raise ValueError("--session-id and --member-token must be provided together.")
    if restore_session_id and restore_member_token:
        updated["session_id"] = str(restore_session_id).strip()
        updated["member_token"] = str(restore_member_token).strip()
        write_config(settings.config_path, updated)
        profile["settings"] = derive_hub_agent_settings(settings=settings, config=updated)
        return profile

    if settings.session_id is None or settings.member_token is None:
        raise ValueError(
            f"{command_name} requires --join-code or an existing session_id/member_token in config."
        )

    write_config(settings.config_path, updated)
    profile["settings"] = derive_hub_agent_settings(settings=settings, config=updated)
    return profile


def emit_runner_event(
    *,
    settings: HubAgentSettings,
    profile: dict[str, Any],
    event: str,
    run_id: str,
    detail: str | None = None,
    status_text: str | None = None,
    task_id: str | None = None,
    outcome: str | None = None,
    summary: str | None = None,
    log_chunk: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/runs/events",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "event": event,
            "run_id": run_id,
            "detail": detail,
            "status_text": status_text,
            "task_id": task_id,
            "outcome": outcome,
            "summary": summary,
            "log_chunk": log_chunk,
            "metadata": metadata,
            **_runner_member_payload(profile=profile),
        },
        token=settings.token,
    )


def publish_runner_waiting(*, settings: HubAgentSettings, profile: dict[str, Any], text: str = "waiting for session activity") -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/status",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "status": "waiting",
            "status_text": text,
            **_runner_member_payload(profile=profile),
        },
        token=settings.token,
    )


def runner_wait_once(*, settings: HubAgentSettings, profile: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/wait",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "timeout_seconds": timeout_seconds,
        },
        token=settings.token,
    )


def _is_wait_already_active_error(message: str) -> bool:
    return "WAIT_ALREADY_ACTIVE" in message or "active wait" in message


def _cancel_wait_for_settings(settings: HubAgentSettings) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/cancel-wait",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
        },
        token=settings.token,
    )


def chief_wait_once_with_self_heal(*, settings: HubAgentSettings, dirs: dict[str, Path], timeout_seconds: float) -> dict[str, Any]:
    profile = {"provider": "chief", "workspace_path": str(dirs["base"])}
    try:
        return runner_wait_once(settings=settings, profile=profile, timeout_seconds=timeout_seconds)
    except ValueError as exc:
        if not _is_wait_already_active_error(str(exc)):
            raise
        cancel_result = _cancel_wait_for_settings(settings)
        retry = runner_wait_once(settings=settings, profile=profile, timeout_seconds=timeout_seconds)
        if isinstance(retry, dict):
            retry = dict(retry)
            retry["self_healed_wait"] = {"status": "cancelled_previous_wait", "cancel_result": cancel_result}
        return retry


def send_runner_reply(
    *,
    settings: HubAgentSettings,
    recipient: str,
    task_id: str | None,
    run_id: str,
    outcome: str,
    summary: str,
    provider: str,
    workspace_path: str,
    metadata: dict[str, Any] | None = None,
    in_reply_to: str | None = None,
) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/send",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "to": recipient,
            "action": "REPLY",
            "payload": build_reply_payload(
                task_id=task_id,
                run_id=run_id,
                outcome=outcome,
                summary=summary,
                provider=provider,
                workspace_path=workspace_path,
                metadata=metadata,
            ),
            "in_reply_to": in_reply_to,
        },
        token=settings.token,
    )


def _runner_state_entry(
    *,
    profile: dict[str, Any],
    settings: HubAgentSettings,
    provider: str,
    workspace_path: str,
) -> tuple[Path, str, dict[str, Any]]:
    state_path: Path = profile["state_path"]
    if settings.session_id is None:
        raise ValueError("session_id is required for runner state.")
    state_key = runner_state_key(
        session_id=settings.session_id,
        agent_name=settings.agent_name,
        provider=provider,
        workspace_path=workspace_path,
    )
    state_entry = load_runner_entry(state_path, key=state_key)
    return state_path, state_key, state_entry


def process_runner_message(*, settings: HubAgentSettings, profile: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    action = message.get("action")
    if action != "TASK":
        payload = {
            "status": "runner_skipped",
            "reason": "non_task_message",
            "message": message,
        }
        emit_json_line(payload)
        publish_runner_waiting(settings=settings, profile=profile)
        return payload

    task = extract_task_spec(
        message=message,
        default_provider=profile["provider"],
        default_workspace=profile["workspace_path"],
    )
    provider = task["provider"]
    workspace_path = task["workspace_path"]
    run_id = str(uuid4())
    state_path, state_key, state_entry = _runner_state_entry(
        profile=profile,
        settings=settings,
        provider=provider,
        workspace_path=workspace_path,
    )
    auto_busy_hold = maybe_start_auto_busy_hold(
        settings=settings,
        message=message,
        default_window_minutes=float(profile.get("auto_busy_heartbeat_minutes") or 0.0),
        interval_seconds=float(profile.get("auto_busy_heartbeat_interval_seconds") or 45.0),
    )

    emit_runner_event(
        settings=settings,
        profile={**profile, "provider": provider, "workspace_path": workspace_path},
        event="RUN_STARTED",
        run_id=run_id,
        detail=f"runner started {provider}",
        status_text=f"runner executing via {provider}",
        task_id=task["task_id"],
        summary=task["instructions"][:240],
        metadata={**(task["metadata"] or {}), **({"auto_busy_hold": auto_busy_hold} if auto_busy_hold is not None else {})},
    )
    save_runner_entry(
        state_path,
        key=state_key,
        entry={
            **state_entry,
            "workspace_path": workspace_path,
            "last_run_status": "running",
            "last_run_started_at": runner_utc_now_iso(),
            "last_run_finished_at": None,
            "last_error": None,
        },
    )

    def _log_callback(stream_name: str, chunk: str) -> None:
        emit_runner_event(
            settings=settings,
            profile={**profile, "provider": provider, "workspace_path": workspace_path},
            event="RUN_LOG",
            run_id=run_id,
            detail=f"{provider} emitted {stream_name}",
            status_text=f"{provider} running",
            task_id=task["task_id"],
            log_chunk=chunk,
        )

    result = execute_provider(
        provider=provider,
        instructions=task["instructions"],
        workspace_path=workspace_path,
        timeout_seconds=profile["task_timeout_seconds"],
        state_entry=state_entry,
        log_callback=_log_callback,
    )
    summary = result.summary or f"{provider} finished with {result.outcome}"
    error_text = result.stderr_text[:512] if result.stderr_text else None
    save_runner_entry(
        state_path,
        key=state_key,
        entry={
            **state_entry,
            "provider_session_id": result.provider_session_id,
            "provider_session_params": result.provider_session_params,
            "workspace_path": workspace_path,
            "last_run_status": result.outcome,
            "last_run_started_at": result.started_at,
            "last_run_finished_at": result.finished_at,
            "last_error": error_text,
        },
    )
    emit_runner_event(
        settings=settings,
        profile={**profile, "provider": provider, "workspace_path": workspace_path},
        event="RUN_FINISHED",
        run_id=run_id,
        detail=f"{provider} run finished",
        status_text=f"runner finished with {result.outcome}",
        task_id=task["task_id"],
        outcome=result.outcome,
        summary=summary,
        metadata={
            **(task["metadata"] or {}),
            **result.metadata,
            "provider_session_id": result.provider_session_id,
        },
    )
    reply_to = task["reply_to"]
    if not isinstance(reply_to, str) or not reply_to.strip():
        raise ValueError("runner task requires a valid reply target.")
    send_result = send_runner_reply(
        settings=settings,
        recipient=reply_to,
        task_id=task["task_id"],
        run_id=run_id,
        outcome=result.outcome,
        summary=summary,
        provider=provider,
        workspace_path=workspace_path,
        metadata={
            **(task["metadata"] or {}),
            **result.metadata,
            "provider_session_id": result.provider_session_id,
        },
        in_reply_to=message.get("id") if isinstance(message.get("id"), str) else None,
    )
    emit_runner_event(
        settings=settings,
        profile={**profile, "provider": provider, "workspace_path": workspace_path},
        event="RUN_REPLY_SENT",
        run_id=run_id,
        detail=f"reply sent to {reply_to}",
        status_text="runner reply sent",
        task_id=task["task_id"],
        outcome=result.outcome,
        summary=summary,
    )
    publish_runner_waiting(settings=settings, profile=profile)
    payload = {
        "status": "runner_completed",
        "run_id": run_id,
        "provider": provider,
        "workspace_path": workspace_path,
        "task_id": task["task_id"],
        "outcome": result.outcome,
        "summary": summary,
        "send_result": send_result,
    }
    if auto_busy_hold is not None:
        payload["auto_busy_hold"] = auto_busy_hold
    emit_json_line(payload)
    return payload


def runner_start(args: argparse.Namespace) -> dict[str, Any]:
    profile = bootstrap_runner_session(args, command_name="runner start")
    settings: HubAgentSettings = profile["settings"]
    publish_runner_waiting(settings=settings, profile=profile)
    last_timeout_at: str | None = None
    while True:
        try:
            response = runner_wait_once(
                settings=settings,
                profile=profile,
                timeout_seconds=profile["wait_timeout_seconds"],
            )
        except ValueError as exc:
            message = str(exc)
            if _is_fatal_session_command_error(message):
                raise
            last_timeout_at = utc_now_rfc3339()
            emit_json_line(
                {
                    "status": "runner_retry",
                    "agent_name": settings.agent_name,
                    "session_id": settings.session_id,
                    "detail": message,
                    "last_retry_at": last_timeout_at,
                }
            )
            time.sleep(profile["retry_delay_seconds"])
            continue

        if response.get("status") == "timeout":
            last_timeout_at = utc_now_rfc3339()
            continue
        if response.get("status") != "message":
            emit_json_line(response)
            continue
        message = response.get("message")
        if not isinstance(message, dict):
            emit_json_line(response)
            continue
        notice = apply_session_notice_if_needed(settings=settings, message=message, target_payload=response)
        if notice is not None:
            emit_json_line(response)
            return response
        process_runner_message(settings=settings, profile=profile, message=message)


def runner_once(args: argparse.Namespace) -> dict[str, Any]:
    profile = bootstrap_runner_session(args, command_name="runner once")
    settings: HubAgentSettings = profile["settings"]
    publish_runner_waiting(settings=settings, profile=profile)
    response = runner_wait_once(
        settings=settings,
        profile=profile,
        timeout_seconds=profile["wait_timeout_seconds"],
    )
    if response.get("status") != "message":
        emit_json_line(response)
        return response
    message = response.get("message")
    if not isinstance(message, dict):
        emit_json_line(response)
        return response
    notice = apply_session_notice_if_needed(settings=settings, message=message, target_payload=response)
    if notice is not None:
        emit_json_line(response)
        return response
    return process_runner_message(settings=settings, profile=profile, message=message)


def _chief_backlog_dirs(settings: HubAgentSettings, args: argparse.Namespace) -> dict[str, Path]:
    raw_backlog_dir = getattr(args, "backlog_dir", None) or get_config_value(settings.config, "chief_backlog_dir")
    base_dir = resolve_config_path(settings.base_dir, raw_backlog_dir or "coord/backlog")
    if base_dir is None:
        base_dir = (settings.base_dir / "coord" / "backlog").resolve()
    pending_dir = base_dir / "pending" if (base_dir / "pending").exists() else base_dir
    assigned_dir = base_dir / "assigned"
    done_dir = base_dir / "done"
    failed_dir = base_dir / "failed"
    ensure_queue_dirs(base_dir, pending_dir, assigned_dir, done_dir, failed_dir)
    return {
        "base": base_dir,
        "pending": pending_dir,
        "assigned": assigned_dir,
        "done": done_dir,
        "failed": failed_dir,
    }


def _chief_pending_task_files(dirs: dict[str, Path]) -> list[Path]:
    pending_dir = dirs["pending"]
    if not pending_dir.exists():
        return []
    return sorted(
        path
        for path in pending_dir.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in {".md", ".txt", ".json"}
        and not path.name.endswith(".assignment.json")
        and not path.name.endswith(".result.json")
    )


def _unique_destination(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    for index in range(1, 10_000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError(f"could not allocate unique destination for {name}.")


def _task_id_from_path(path: Path) -> str:
    stem = path.name
    for suffix in (".task.md", ".task.txt", ".json", ".md", ".txt"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.strip() or path.stem


def _load_chief_task(path: Path, *, default_provider: str | None, default_workspace: str | None) -> dict[str, Any]:
    task_id = _task_id_from_path(path)
    metadata: dict[str, Any] = {"source_file": path.name}
    provider = default_provider
    workspace_path = default_workspace
    if path.suffix.lower() == ".json":
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"task file {path} must contain a JSON object.")
        raw_task_id = parsed.get("task_id")
        if isinstance(raw_task_id, str) and raw_task_id.strip():
            task_id = raw_task_id.strip()
        instructions = parsed.get("instructions") or parsed.get("payload") or parsed.get("content")
        if isinstance(parsed.get("provider"), str) and parsed["provider"].strip():
            provider = parsed["provider"].strip()
        if isinstance(parsed.get("workspace_path"), str) and parsed["workspace_path"].strip():
            workspace_path = normalize_workspace_path(parsed["workspace_path"])
        if isinstance(parsed.get("metadata"), dict):
            metadata.update(parsed["metadata"])
        required_capabilities = normalize_capabilities(
            parsed.get("required_capabilities")
            if parsed.get("required_capabilities") is not None
            else parsed.get("required_role") or parsed.get("tags")
        )
        verify_command = parsed.get("verify_command")
        verify_timeout_seconds = parsed.get("verify_timeout_seconds")
        acceptance_criteria = parsed.get("acceptance_criteria") or parsed.get("verify_prompt")
        judge_provider = parsed.get("judge_provider")
        judge_timeout_seconds = parsed.get("judge_timeout_seconds")
        max_attempts = parsed.get("max_attempts")
    else:
        instructions = path.read_text(encoding="utf-8").strip()
        required_capabilities = []
        verify_command = None
        verify_timeout_seconds = None
        acceptance_criteria = None
        judge_provider = None
        judge_timeout_seconds = None
        max_attempts = None
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError(f"task file {path} does not include instructions.")
    return {
        "task_id": task_id,
        "instructions": instructions.strip(),
        "provider": provider,
        "workspace_path": workspace_path,
        "metadata": metadata,
        "required_capabilities": required_capabilities,
        "verify_command": verify_command,
        "verify_timeout_seconds": verify_timeout_seconds,
        "acceptance_criteria": acceptance_criteria.strip() if isinstance(acceptance_criteria, str) and acceptance_criteria.strip() else None,
        "judge_provider": judge_provider.strip() if isinstance(judge_provider, str) and judge_provider.strip() else None,
        "judge_timeout_seconds": judge_timeout_seconds,
        "max_attempts": max_attempts,
    }


def _assigned_task_candidates(dirs: dict[str, Path], task_id: str) -> list[Path]:
    assigned_dir = dirs["assigned"]
    if not assigned_dir.exists():
        return []
    normalized = task_id.strip()
    candidates = {
        path
        for path in assigned_dir.iterdir()
        if path.is_file()
        and (_task_id_from_path(path) == normalized or path.stem == normalized or path.name.startswith(f"{normalized}."))
        and not path.name.endswith(".assignment.json")
        and not path.name.endswith(".result.json")
    }
    for _, assignment in _assignment_records_for_task(dirs, normalized):
        task_file = assignment.get("task_file")
        if isinstance(task_file, str) and task_file.strip():
            task_path = assigned_dir / task_file
            if task_path.exists() and task_path.is_file():
                candidates.add(task_path)
    return sorted(candidates, key=lambda path: str(path))


def _assignment_records_for_task(dirs: dict[str, Path], task_id: str) -> list[tuple[Path, dict[str, Any]]]:
    assigned_dir = dirs["assigned"]
    if not assigned_dir.exists():
        return []
    normalized = task_id.strip()
    records: list[tuple[Path, dict[str, Any]]] = []
    for assignment_path in sorted(assigned_dir.glob("*.assignment.json")):
        try:
            assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(assignment, dict):
            continue
        if str(assignment.get("task_id") or "").strip() == normalized:
            records.append((assignment_path, assignment))
    return records


def _move_assignment_records_for_task(dirs: dict[str, Path], task_id: str, target_dir: Path) -> list[str]:
    moved: list[str] = []
    for assignment_path, _ in _assignment_records_for_task(dirs, task_id):
        if not assignment_path.exists():
            continue
        destination = _unique_destination(target_dir, assignment_path.name)
        assignment_path.replace(destination)
        moved.append(str(destination))
    return moved


def _parse_message_payload_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            return {"summary": payload.strip()}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _infer_reply_outcome(payload: dict[str, Any]) -> tuple[str, bool]:
    raw_outcome = payload.get("outcome")
    if isinstance(raw_outcome, str) and raw_outcome.strip():
        return raw_outcome.strip().lower(), False
    text_parts = [
        payload.get("summary"),
        payload.get("text"),
        payload.get("message"),
        payload.get("result"),
    ]
    text = " ".join(str(part).strip() for part in text_parts if isinstance(part, str) and part.strip()).strip()
    if not text:
        return "unknown", False
    normalized = text.lower().lstrip("✅☑️✔︎✔:;,.! \t\r\n")
    if re.match(r"^(done|success|succeeded|passed|pass|complete|completed|ok|ready)\b", normalized):
        return "success", True
    if re.match(r"^(failed|fail|error|errored|blocked|cannot|can't|unable)\b", normalized):
        return "failed", True
    return "unknown", False


def _chief_infer_task_id_for_worker(*, dirs: dict[str, Path], worker: Any) -> str | None:
    if not isinstance(worker, str) or not worker.strip():
        return None
    assigned_dir = dirs["assigned"]
    if not assigned_dir.exists():
        return None
    matches: list[str] = []
    for assignment_path in assigned_dir.glob("*.assignment.json"):
        try:
            assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(assignment, dict) or assignment.get("worker") != worker:
            continue
        task_id = assignment.get("task_id")
        task_file = assignment.get("task_file")
        if isinstance(task_id, str) and task_id.strip():
            if isinstance(task_file, str) and task_file.strip() and not (assigned_dir / task_file).exists():
                continue
            matches.append(task_id.strip())
    unique_matches = sorted(set(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def _parse_rfc3339_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _chief_assignment_ttl_seconds(settings: HubAgentSettings, args: argparse.Namespace) -> float:
    raw_value = (
        getattr(args, "assignment_ttl_seconds", None)
        if getattr(args, "assignment_ttl_seconds", None) is not None
        else get_config_value(settings.config, "chief_assignment_ttl_seconds")
    )
    return float(raw_value if raw_value is not None else 1800.0)


def _chief_requeue_expired_assignments(*, dirs: dict[str, Path], ttl_seconds: float) -> list[dict[str, Any]]:
    if ttl_seconds <= 0:
        return []
    assigned_dir = dirs["assigned"]
    if not assigned_dir.exists():
        return []
    now = datetime.now(timezone.utc)
    expired: list[dict[str, Any]] = []
    for assignment_path in sorted(assigned_dir.glob("*.assignment.json")):
        try:
            assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(assignment, dict):
            continue
        assigned_at = _parse_rfc3339_timestamp(assignment.get("assigned_at"))
        if assigned_at is None or (now - assigned_at).total_seconds() < ttl_seconds:
            continue
        task_file = assignment.get("task_file")
        task_id = assignment.get("task_id")
        task_path = assigned_dir / str(task_file) if isinstance(task_file, str) and task_file.strip() else None
        if task_path is None or not task_path.exists():
            continue
        feedback = (
            f"Assignment TTL expired after {ttl_seconds:g} seconds without a valid REPLY. "
            "Re-run the task and report with the same task_id."
        )
        requeued = _requeue_task_with_feedback(
            task_path=task_path,
            pending_dir=dirs["pending"],
            verify_result={"status": "failed", "reason": "assignment_ttl_expired", "ttl_seconds": ttl_seconds},
            reply_payload={"summary": feedback},
            feedback_text=feedback,
        )
        assignment_path.unlink(missing_ok=True)
        result_path = _unique_destination(dirs["failed"], f"{str(task_id or _task_id_from_path(task_path))}.result.json")
        write_json_atomic(
            result_path,
            {
                "task_id": str(task_id or _task_id_from_path(task_path)),
                "outcome": "assignment_ttl_expired",
                "worker": assignment.get("worker"),
                "assigned_at": assignment.get("assigned_at"),
                "ttl_seconds": ttl_seconds,
                "recorded_at": utc_now_rfc3339(),
                "requeued_task_file": str(requeued),
                "assignment_path": str(assignment_path),
            },
        )
        expired.append(
            {
                "task_id": str(task_id or _task_id_from_path(task_path)),
                "worker": assignment.get("worker"),
                "requeued_task_file": str(requeued),
                "result_path": str(result_path),
            }
        )
    return expired


def _tail_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    else:
        value = str(value)
    if len(value) <= limit:
        return value
    return value[-limit:]


def _chief_run_verify(task: dict[str, Any]) -> dict[str, Any]:
    verify_command = task.get("verify_command")
    if verify_command is None:
        return {"status": "skipped", "reason": "no_verify_command"}
    if isinstance(verify_command, list):
        command = [str(item) for item in verify_command if str(item).strip()]
        if not command:
            return {"status": "failed", "reason": "invalid_verify_command"}
        shell = False
    elif isinstance(verify_command, str) and verify_command.strip():
        command = verify_command.strip()
        shell = True
    else:
        return {"status": "failed", "reason": "invalid_verify_command"}
    raw_timeout = task.get("verify_timeout_seconds")
    try:
        timeout_seconds = float(raw_timeout) if raw_timeout is not None else 600.0
    except (TypeError, ValueError):
        timeout_seconds = 600.0
    timeout_seconds = max(timeout_seconds, 1.0)
    cwd = task.get("workspace_path")
    try:
        result = subprocess.run(
            command,
            cwd=cwd if isinstance(cwd, str) and cwd.strip() else None,
            text=True,
            capture_output=True,
            shell=shell,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "failed",
            "reason": "timeout",
            "command": verify_command,
            "timeout_seconds": timeout_seconds,
            "stdout_tail": _tail_text(exc.stdout or ""),
            "stderr_tail": _tail_text(exc.stderr or ""),
        }
    except OSError as exc:
        return {
            "status": "failed",
            "reason": "execution_error",
            "command": verify_command,
            "error": str(exc),
        }
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "command": verify_command,
        "exit_code": result.returncode,
        "stdout_tail": _tail_text(result.stdout or ""),
        "stderr_tail": _tail_text(result.stderr or ""),
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
        return dict(parsed) if isinstance(parsed, dict) else None
    except (ValueError, json.JSONDecodeError):
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except (ValueError, json.JSONDecodeError):
            return None
        return dict(parsed) if isinstance(parsed, dict) else None
    return None


def _chief_judge_prompt(*, task: dict[str, Any], reply_payload: dict[str, Any], verify_result: dict[str, Any]) -> str:
    return (
        "You are the ACP autonomous chief judge. Evaluate whether the worker result satisfies the task.\n"
        "Return ONLY JSON with this shape: {\"pass\": true|false, \"feedback\": \"short actionable feedback\"}.\n\n"
        f"Task id: {task.get('task_id')}\n"
        f"Instructions:\n{task.get('instructions')}\n\n"
        f"Acceptance criteria:\n{task.get('acceptance_criteria')}\n\n"
        f"Worker reply JSON:\n{json.dumps(reply_payload, ensure_ascii=False, indent=2)}\n\n"
        f"Mechanical verification JSON:\n{json.dumps(verify_result, ensure_ascii=False, indent=2)}\n"
    )


def _chief_run_judge(*, task: dict[str, Any], reply_payload: dict[str, Any], verify_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(task.get("acceptance_criteria"), str) or not task["acceptance_criteria"].strip():
        return {"status": "skipped", "reason": "no_acceptance_criteria"}
    provider = task.get("judge_provider") or task.get("provider") or "claude_local"
    if provider not in {"claude_local", "codex_local"}:
        return {"status": "failed", "reason": "invalid_judge_provider", "provider": provider}
    raw_timeout = task.get("judge_timeout_seconds")
    try:
        timeout_seconds = float(raw_timeout) if raw_timeout is not None else 600.0
    except (TypeError, ValueError):
        timeout_seconds = 600.0
    timeout_seconds = max(timeout_seconds, 1.0)
    workspace_path = task.get("workspace_path") if isinstance(task.get("workspace_path"), str) else "."
    result = execute_provider(
        provider=provider,
        instructions=_chief_judge_prompt(task=task, reply_payload=reply_payload, verify_result=verify_result),
        workspace_path=workspace_path,
        timeout_seconds=timeout_seconds,
        state_entry={},
    )
    parsed = _extract_json_object(result.stdout_text or result.stderr_text or "")
    if result.outcome != "success":
        return {
            "status": "failed",
            "reason": "judge_provider_failed",
            "provider": provider,
            "outcome": result.outcome,
            "exit_code": result.exit_code,
            "stdout_tail": _tail_text(result.stdout_text),
            "stderr_tail": _tail_text(result.stderr_text),
        }
    if parsed is None:
        return {
            "status": "failed",
            "reason": "judge_invalid_json",
            "provider": provider,
            "stdout_tail": _tail_text(result.stdout_text),
            "stderr_tail": _tail_text(result.stderr_text),
        }
    passed = bool(parsed.get("pass") if "pass" in parsed else parsed.get("passed") or parsed.get("accepted"))
    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        feedback = "Judge rejected the result but did not provide feedback." if not passed else ""
    return {
        "status": "passed" if passed else "failed",
        "provider": provider,
        "feedback": feedback.strip(),
        "raw": parsed,
        "stdout_tail": _tail_text(result.stdout_text),
        "stderr_tail": _tail_text(result.stderr_text),
    }


def _judge_feedback_text(*, judge_result: dict[str, Any], reply_payload: dict[str, Any]) -> str:
    feedback = judge_result.get("feedback")
    parts = ["Chief semantic judge rejected the worker result."]
    if isinstance(feedback, str) and feedback.strip():
        parts.append(feedback.strip())
    if reply_payload.get("summary"):
        parts.append(f"Worker summary: {reply_payload.get('summary')}")
    if judge_result.get("reason"):
        parts.append(f"Judge reason: {judge_result.get('reason')}")
    return "\n\n".join(str(part) for part in parts if str(part).strip())


def _verification_feedback_text(*, verify_result: dict[str, Any], reply_payload: dict[str, Any]) -> str:
    parts = ["Chief verification failed after the worker reported success."]
    if reply_payload.get("summary"):
        parts.append(f"Worker summary: {reply_payload.get('summary')}")
    if verify_result.get("command"):
        parts.append(f"Verify command: {verify_result.get('command')}")
    if verify_result.get("exit_code") is not None:
        parts.append(f"Exit code: {verify_result.get('exit_code')}")
    if verify_result.get("reason"):
        parts.append(f"Reason: {verify_result.get('reason')}")
    if verify_result.get("stderr_tail"):
        parts.append(f"stderr:\n{verify_result.get('stderr_tail')}")
    if verify_result.get("stdout_tail"):
        parts.append(f"stdout:\n{verify_result.get('stdout_tail')}")
    return "\n\n".join(str(part) for part in parts if str(part).strip())


def _task_attempt_number(task: dict[str, Any]) -> int:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    try:
        feedback_count = int(metadata.get("feedback_count") or 0)
    except (TypeError, ValueError):
        feedback_count = 0
    return max(feedback_count, 0) + 1


def _task_max_attempts(task: dict[str, Any]) -> int | None:
    raw_value = task.get("max_attempts")
    if raw_value is None:
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _task_attempts_exhausted(task: dict[str, Any]) -> bool:
    max_attempts = _task_max_attempts(task)
    return max_attempts is not None and _task_attempt_number(task) >= max_attempts


def _requeue_task_with_feedback(
    *,
    task_path: Path,
    pending_dir: Path,
    verify_result: dict[str, Any],
    reply_payload: dict[str, Any],
    feedback_text: str | None = None,
    judge_result: dict[str, Any] | None = None,
) -> Path:
    feedback = feedback_text or _verification_feedback_text(verify_result=verify_result, reply_payload=reply_payload)
    destination = _unique_destination(pending_dir, task_path.name)
    if task_path.suffix.lower() == ".json":
        try:
            parsed = json.loads(task_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            old_instructions = parsed.get("instructions") or parsed.get("payload") or parsed.get("content") or ""
            parsed["instructions"] = (
                f"{feedback}\n\n"
                "Apply the correction and re-report with the same task_id.\n\n"
                f"Original instructions:\n{old_instructions}"
            ).strip()
            metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
            metadata = dict(metadata)
            metadata["chief_feedback"] = feedback
            metadata["feedback_count"] = int(metadata.get("feedback_count") or 0) + 1
            if judge_result is not None:
                history = metadata.get("judge_history") if isinstance(metadata.get("judge_history"), list) else []
                history.append(judge_result)
                metadata["judge_history"] = history[-10:]
            parsed["metadata"] = metadata
            write_json_atomic(destination, parsed)
            task_path.unlink(missing_ok=True)
            return destination
    original = task_path.read_text(encoding="utf-8")
    destination.write_text(
        (
            f"{feedback}\n\n"
            "Apply the correction and re-report with the same task_id.\n\n"
            f"Original instructions:\n{original}"
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    task_path.unlink(missing_ok=True)
    return destination


def _chief_record_reply(*, dirs: dict[str, Path], message: dict[str, Any]) -> dict[str, Any]:
    payload = _parse_message_payload_object(message.get("payload"))
    task_id = payload.get("task_id")
    inferred_task_id = False
    if not isinstance(task_id, str) or not task_id.strip():
        inferred = _chief_infer_task_id_for_worker(dirs=dirs, worker=message.get("from"))
        if inferred is None:
            return {"status": "ignored", "reason": "reply_without_task_id"}
        task_id = inferred
        payload["task_id"] = task_id
        inferred_task_id = True
    outcome, inferred_outcome = _infer_reply_outcome(payload)
    reported_success = outcome in {"success", "succeeded", "ok", "passed", "completed", "done"}
    candidates = _assigned_task_candidates(dirs, task_id.strip())
    verify_result = {"status": "skipped", "reason": "no_assigned_task_file"}
    judge_result = {"status": "skipped", "reason": "not_run"}
    assigned_task: dict[str, Any] | None = None
    attempt_number: int | None = None
    max_attempts: int | None = None
    if reported_success and candidates:
        try:
            assigned_task = _load_chief_task(candidates[0], default_provider=None, default_workspace=None)
            attempt_number = _task_attempt_number(assigned_task)
            max_attempts = _task_max_attempts(assigned_task)
            verify_result = _chief_run_verify(assigned_task)
            if verify_result.get("status") != "failed":
                judge_result = _chief_run_judge(task=assigned_task, reply_payload=payload, verify_result=verify_result)
        except Exception as exc:
            verify_result = {"status": "failed", "reason": "verify_setup_error", "error": str(exc)}
    verification_failed = reported_success and verify_result.get("status") == "failed"
    judge_failed = reported_success and not verification_failed and judge_result.get("status") == "failed"
    needs_requeue = verification_failed or judge_failed
    attempts_exhausted = bool(needs_requeue and assigned_task is not None and _task_attempts_exhausted(assigned_task))
    target_dir = dirs["failed"] if attempts_exhausted or not reported_success else dirs["done"]
    result_dir = dirs["failed"] if needs_requeue or not reported_success else dirs["done"]
    moved_to: str | None = None
    requeued_to: str | None = None
    moved_assignments: list[str] = []
    if candidates:
        if needs_requeue and not attempts_exhausted:
            feedback = (
                _judge_feedback_text(judge_result=judge_result, reply_payload=payload)
                if judge_failed
                else _verification_feedback_text(verify_result=verify_result, reply_payload=payload)
            )
            requeued = _requeue_task_with_feedback(
                task_path=candidates[0],
                pending_dir=dirs["pending"],
                verify_result=verify_result,
                reply_payload=payload,
                feedback_text=feedback,
                judge_result=judge_result if judge_failed else None,
            )
            requeued_to = str(requeued)
            moved_assignments = _move_assignment_records_for_task(dirs, task_id.strip(), result_dir)
        else:
            target = _unique_destination(target_dir, candidates[0].name)
            candidates[0].replace(target)
            moved_to = str(target)
            moved_assignments = _move_assignment_records_for_task(dirs, task_id.strip(), target_dir)
    effective_outcome = outcome
    if verification_failed:
        effective_outcome = "verification_failed"
    elif judge_failed:
        effective_outcome = "judge_failed"
    result_path = _unique_destination(result_dir, f"{task_id.strip()}.result.json")
    write_json_atomic(
        result_path,
        {
            "task_id": task_id.strip(),
            "outcome": effective_outcome,
            "reported_outcome": outcome,
            "inferred_outcome": inferred_outcome,
            "from": message.get("from"),
            "message_id": message.get("id"),
            "payload": payload,
            "verify_result": verify_result,
            "judge_result": judge_result,
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "attempts_exhausted": attempts_exhausted,
            "inferred_task_id": inferred_task_id,
            "recorded_at": utc_now_rfc3339(),
            "moved_task_file": moved_to,
            "requeued_task_file": requeued_to,
            "moved_assignment_files": moved_assignments,
        },
    )
    return {
        "status": "recorded",
        "task_id": task_id.strip(),
        "outcome": effective_outcome,
        "reported_outcome": outcome,
        "inferred_outcome": inferred_outcome,
        "verify_result": verify_result,
        "judge_result": judge_result,
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "attempts_exhausted": attempts_exhausted,
        "inferred_task_id": inferred_task_id,
        "result_path": str(result_path),
        "moved_task_file": moved_to,
        "requeued_task_file": requeued_to,
        "moved_assignment_files": moved_assignments,
    }


def _chief_fetch_session_snapshot(settings: HubAgentSettings) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    route = (
        f"/sessions/{settings.session_id}"
        f"?agent_name={urllib.parse.quote(settings.agent_name)}"
        f"&member_token={urllib.parse.quote(settings.member_token)}"
    )
    response = get_json(hub_http=settings.hub_http, route=route, token=settings.token)
    session = response.get("session")
    if not isinstance(session, dict):
        raise ValueError("session snapshot did not include a session object.")
    return session


def _chief_available_workers(session: dict[str, Any], *, chief_name: str) -> list[dict[str, Any]]:
    members = session.get("members")
    if not isinstance(members, list):
        return []
    workers: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        agent_name = member.get("agent_name")
        if not isinstance(agent_name, str) or not agent_name.strip() or agent_name == chief_name:
            continue
        if member.get("role") == "chief":
            continue
        if member.get("status") != "waiting":
            continue
        if member.get("heartbeat_state") not in {None, "live"}:
            continue
        if int(member.get("pending_count") or 0) > 0:
            continue
        if member.get("current_task"):
            continue
        workers.append(member)
    return sorted(workers, key=lambda item: str(item.get("agent_name") or ""))


def _member_capabilities(member: dict[str, Any]) -> set[str]:
    try:
        return set(normalize_capabilities(member.get("capabilities")))
    except ValueError:
        return set()


def _select_worker_for_task(workers: list[dict[str, Any]], task: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    required = set(normalize_capabilities(task.get("required_capabilities")))
    if required:
        for index, worker in enumerate(workers):
            if required.issubset(_member_capabilities(worker)):
                return index, worker
    return 0, workers[0]


def _chief_send_task(
    *,
    settings: HubAgentSettings,
    worker: str,
    task: dict[str, Any],
    task_path: Path,
    assigned_path: Path,
) -> dict[str, Any]:
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("session_id and member_token are required in config. Create or join a session first.")
    metadata = dict(task.get("metadata") if isinstance(task.get("metadata"), dict) else {})
    metadata.update({"assigned_file": assigned_path.name, "original_file": task_path.name})
    task_payload = {
        "task_id": task["task_id"],
        "instructions": task["instructions"],
        "reply_to": settings.agent_name,
        "metadata": metadata,
    }
    if task.get("required_capabilities"):
        task_payload["required_capabilities"] = task["required_capabilities"]
    if isinstance(task.get("acceptance_criteria"), str) and task["acceptance_criteria"].strip():
        task_payload["acceptance_criteria"] = task["acceptance_criteria"].strip()
    if isinstance(task.get("provider"), str) and task["provider"].strip():
        task_payload["provider"] = task["provider"].strip()
    if isinstance(task.get("workspace_path"), str) and task["workspace_path"].strip():
        task_payload["workspace_path"] = task["workspace_path"].strip()
    return post_json(
        hub_http=settings.hub_http,
        route="/sessions/send",
        payload={
            "session_id": settings.session_id,
            "agent_name": settings.agent_name,
            "member_token": settings.member_token,
            "to": worker,
            "action": "TASK",
            "payload": json.dumps(task_payload, ensure_ascii=True),
        },
        token=settings.token,
    )


def _chief_dispatch_backlog(settings: HubAgentSettings, args: argparse.Namespace, *, session: dict[str, Any], dirs: dict[str, Path]) -> list[dict[str, Any]]:
    default_provider = getattr(args, "provider", None) or get_config_value(settings.config, "chief_default_provider")
    default_workspace = getattr(args, "workspace", None) or get_config_value(settings.config, "chief_default_workspace", "runner_workspace", "workspace_path")
    if isinstance(default_workspace, str) and default_workspace.strip():
        default_workspace = normalize_workspace_path(default_workspace)
    else:
        default_workspace = None
    dispatched: list[dict[str, Any]] = []
    pending = _chief_pending_task_files(dirs)
    workers = _chief_available_workers(session, chief_name=settings.agent_name)
    for task_path in pending:
        if not workers:
            break
        try:
            task = _load_chief_task(task_path, default_provider=default_provider, default_workspace=default_workspace)
        except Exception as exc:
            failed_path = _unique_destination(dirs["failed"], task_path.name)
            task_path.replace(failed_path)
            result_path = _unique_destination(dirs["failed"], f"{_task_id_from_path(task_path)}.result.json")
            write_json_atomic(
                result_path,
                {
                    "task_id": _task_id_from_path(task_path),
                    "outcome": "invalid_task",
                    "error": str(exc),
                    "recorded_at": utc_now_rfc3339(),
                    "moved_task_file": str(failed_path),
                },
            )
            dispatched.append(
                {
                    "task_id": _task_id_from_path(task_path),
                    "worker": None,
                    "task_file": str(failed_path),
                    "status": "invalid_task",
                    "error": str(exc),
                    "result_path": str(result_path),
                }
            )
            continue
        worker_index, worker_member = _select_worker_for_task(workers, task)
        worker_name = str(worker_member["agent_name"])
        assigned_path = _unique_destination(dirs["assigned"], task_path.name)
        task_path.replace(assigned_path)
        try:
            send_result = _chief_send_task(
                settings=settings,
                worker=worker_name,
                task=task,
                task_path=task_path,
                assigned_path=assigned_path,
            )
        except Exception:
            rollback_path = _unique_destination(dirs["pending"], task_path.name)
            assigned_path.replace(rollback_path)
            raise
        assignment_path = _unique_destination(dirs["assigned"], f"{task['task_id']}.assignment.json")
        write_json_atomic(
            assignment_path,
            {
                "task_id": task["task_id"],
                "worker": worker_name,
                "worker_capabilities": sorted(_member_capabilities(worker_member)),
                "required_capabilities": task.get("required_capabilities") or [],
                "assigned_at": utc_now_rfc3339(),
                "task_file": assigned_path.name,
                "send_result": send_result,
            },
        )
        dispatched.append(
            {
                "task_id": task["task_id"],
                "worker": worker_name,
                "worker_capabilities": sorted(_member_capabilities(worker_member)),
                "required_capabilities": task.get("required_capabilities") or [],
                "task_file": str(assigned_path),
                "assignment_path": str(assignment_path),
                "send_result": send_result,
            }
        )
        workers.pop(worker_index)
    return dispatched


def chief_once(args: argparse.Namespace) -> dict[str, Any]:
    settings = resolve_hub_agent_settings(args)
    if settings.session_id is None or settings.member_token is None:
        raise ValueError("chief requires an active session_id/member_token in config. Create or join a session first.")
    dirs = _chief_backlog_dirs(settings, args)
    expired_assignments = _chief_requeue_expired_assignments(
        dirs=dirs,
        ttl_seconds=_chief_assignment_ttl_seconds(settings, args),
    )
    safe_update_session_status(settings=settings, state="waiting", text="chief waiting for worker reports")
    message_result: dict[str, Any] | None = None
    timeout_seconds = float(getattr(args, "wait_timeout_seconds", 0.0) or 0.0)
    if timeout_seconds > 0:
        wait_response = chief_wait_once_with_self_heal(settings=settings, dirs=dirs, timeout_seconds=min(timeout_seconds, 300.0))
        if wait_response.get("status") == "message" and isinstance(wait_response.get("message"), dict):
            message = wait_response["message"]
            notice = apply_session_notice_if_needed(settings=settings, message=message, target_payload=wait_response)
            if notice is not None:
                return wait_response
            if message.get("action") == "REPLY":
                message_result = _chief_record_reply(dirs=dirs, message=message)
            else:
                message_result = {"status": "observed", "action": message.get("action"), "from": message.get("from")}
        elif wait_response.get("status") != "timeout":
            message_result = wait_response
    session = _chief_fetch_session_snapshot(settings)
    dispatched = _chief_dispatch_backlog(settings, args, session=session, dirs=dirs)
    remaining_pending = len(_chief_pending_task_files(dirs))
    result = {
        "status": "chief_tick",
        "agent_name": settings.agent_name,
        "session_id": settings.session_id,
        "message_result": message_result,
        "expired_assignments": expired_assignments,
        "expired_assignment_count": len(expired_assignments),
        "dispatched": dispatched,
        "dispatched_count": len(dispatched),
        "remaining_pending": remaining_pending,
        "backlog_dir": str(dirs["base"]),
    }
    if remaining_pending == 0 and not dispatched:
        result["escalation"] = "backlog_empty"
    return result


def chief_start(args: argparse.Namespace) -> dict[str, Any]:
    if bool(getattr(args, "once", False)):
        return chief_once(args)
    tick_seconds = max(float(getattr(args, "tick_seconds", 2.0) or 2.0), 0.1)
    while True:
        try:
            payload = chief_once(args)
            emit_json_line(payload)
        except ValueError as exc:
            if _is_fatal_session_command_error(str(exc)):
                raise
            emit_json_line({"status": "chief_retry", "detail": str(exc), "retry_at": utc_now_rfc3339()})
        time.sleep(tick_seconds)


def init_from_args(args: argparse.Namespace) -> dict[str, Any]:
    command = [sys.executable, str((ACP_ROOT / "install_from_bundle.py").resolve())]
    for value in getattr(args, "agent", None) or []:
        command.extend(["--agent", value])
    if getattr(args, "hub_mode", None):
        command.extend(["--hub-mode", args.hub_mode])
    if getattr(args, "hub_http", None):
        command.extend(["--hub-http", args.hub_http])
    if getattr(args, "hub_ws", None):
        command.extend(["--hub-ws", args.hub_ws])
    if getattr(args, "token", None) is not None:
        command.extend(["--token", args.token])
    if getattr(args, "skill_home", None):
        command.extend(["--skill-home", args.skill_home])
    if getattr(args, "skip_install_deps", False):
        command.append("--skip-install-deps")
    if getattr(args, "force", False):
        command.append("--force")
    if getattr(args, "non_interactive", False):
        command.append("--non-interactive")

    result = subprocess.run(
        command,
        cwd=str(ACP_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "installer failed"
        raise ValueError(detail)
    output = result.stdout.strip()
    if not output:
        return {"status": "ok"}
    try:
        parsed = json.loads(output)
    except (ValueError, json.JSONDecodeError):
        return {"status": "ok", "detail": output}
    if not isinstance(parsed, dict):
        return {"status": "ok", "detail": output}
    return parsed


def task_from_args(args: argparse.Namespace) -> dict[str, Any]:
    args.action = "TASK"
    args.payload = resolve_send_payload_text(args)
    args.payload_file = None  # consumed above; prevent a second read (esp. stdin) downstream
    return dispatch_send(args)


def reply_from_args(args: argparse.Namespace) -> dict[str, Any]:
    args.action = "REPLY"
    args.payload = resolve_send_payload_text(args)
    args.payload_file = None  # consumed above; prevent a second read (esp. stdin) downstream
    return dispatch_send(args)


async def run_client_from_args(args: argparse.Namespace) -> None:
    settings = resolve_runtime_settings(args)
    runtime = ACPClientRuntime(
        agent_name=settings.agent_name,
        hub_ws=settings.hub_ws,
        inbox_dir=settings.inbox_dir,
        outbox_dir=settings.outbox_dir,
        sent_dir=settings.sent_dir,
        token=settings.token,
        poll_ms=settings.poll_ms,
        backoff=settings.backoff,
        connect_timeout=settings.connect_timeout,
    )
    try:
        await runtime.run()
    except asyncio.CancelledError:
        runtime.stop()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "run":
            resolve_runtime_settings(args)
        elif args.command == "init":
            pass
        elif args.command == "runner":
            resolve_runner_profile(args)
        elif args.command == "chief":
            resolve_hub_agent_settings(args)
        elif args.command in {"create-session", "join-session", "start", "join", "managed-start", "managed-join", "onboard", "connect", "coordinate", "attach-session", "wait", "cancel-wait", "wait-window", "listen", "status", "heartbeat", "session-info", "leave-session", "send", "task", "reply"}:
            resolve_hub_agent_settings(args)
        elif args.command == "invite":
            pass
        elif args.command == "onboard-help":
            pass
        elif args.command in {"managed-sessions", "managed-close"}:
            managed_command_hub_http_from_args(args, command_name=args.command)
        elif args.command in {"update-check", "self-update"}:
            _resolve_hub_http_simple(args)
    except (ValueError, OSError) as exc:
        parser.error(_with_orientation_hint(str(exc)))
        return 2

    try:
        if args.command == "init":
            print(json.dumps(init_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "quickstart":
            emit_json_line(quickstart_from_args(args))
            return 0
        if args.command == "hub-up":
            emit_json_line(
                ensure_local_hub_running(
                    host=args.host,
                    port=args.port,
                    startup_timeout_seconds=getattr(args, "startup_timeout_seconds", 15.0),
                )
            )
            return 0
        if args.command == "hub-down":
            emit_json_line(stop_local_hub())
            return 0
        if args.command == "hub-status":
            emit_json_line(local_hub_status())
            return 0
        if args.command == "send":
            print(json.dumps(dispatch_send(args), ensure_ascii=True))
            return 0
        if args.command == "task":
            print(json.dumps(task_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "reply":
            print(json.dumps(reply_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "create-session":
            if getattr(args, "listen", False):
                create_session_and_optionally_listen(args, listen_after=True)
            else:
                print(json.dumps(create_session_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "join-session":
            if getattr(args, "listen", False):
                join_session_and_optionally_listen(args, listen_after=True)
            else:
                print(json.dumps(join_session_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "start":
            create_session_and_optionally_listen(args, listen_after=not bool(getattr(args, "no_listen", False)))
            return 0
        if args.command == "join":
            join_session_and_optionally_listen(args, listen_after=not bool(getattr(args, "no_listen", False)))
            return 0
        if args.command == "managed-start":
            managed_start_and_optionally_listen(args, listen_after=not bool(getattr(args, "no_listen", False)))
            return 0
        if args.command == "managed-join":
            managed_join_and_optionally_listen(args, listen_mode=_managed_join_listen_mode(args))
            return 0
        if args.command == "managed-sessions":
            print(json.dumps(managed_sessions_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "managed-close":
            print(json.dumps(managed_close_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "onboard":
            print(json.dumps(onboard_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "connect":
            print(json.dumps(connect_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "coordinate":
            print(json.dumps(coordinate_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "invite":
            print(json.dumps(invite_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "onboard-help":
            print(json.dumps(onboard_help_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "attach-session":
            attach_session_and_optionally_listen(args, listen_after=not bool(getattr(args, "no_listen", False)))
            return 0
        if args.command == "wait":
            print(json.dumps(wait_for_session_message(args), ensure_ascii=True))
            return 0
        if args.command == "cancel-wait":
            print(json.dumps(cancel_session_wait(args), ensure_ascii=True))
            return 0
        if args.command == "wait-window":
            print(json.dumps(wait_window_for_session_message(args), ensure_ascii=True))
            return 0
        if args.command == "listen":
            listen_for_session_message(args)
            return 0
        if args.command == "status":
            print(json.dumps(update_session_status(args), ensure_ascii=True))
            return 0
        if args.command == "heartbeat":
            print(json.dumps(heartbeat_session(args), ensure_ascii=True))
            return 0
        if args.command == "leave-session":
            print(json.dumps(leave_session_from_args(args), ensure_ascii=True))
            return 0
        if args.command == "session-info":
            print(json.dumps(fetch_session_info(args), ensure_ascii=True))
            return 0
        if args.command == "update-check":
            print(json.dumps(cmd_update_check(args), ensure_ascii=True))
            return 0
        if args.command == "self-update":
            print(json.dumps(cmd_self_update(args), ensure_ascii=True))
            return 0
        if args.command == "health":
            print(json.dumps(cmd_health(args), ensure_ascii=True))
            return 0
        if args.command == "agents":
            print(json.dumps(cmd_agents(args), ensure_ascii=True))
            return 0
        if args.command == "overview":
            print(json.dumps(cmd_overview(args), ensure_ascii=True))
            return 0
        if args.command == "sessions":
            print(json.dumps(cmd_sessions(args), ensure_ascii=True))
            return 0
        if args.command == "replay":
            print(json.dumps(cmd_replay(args), ensure_ascii=True))
            return 0
        if args.command == "doctor":
            result = cmd_doctor(args)
            print(json.dumps(result, ensure_ascii=True))
            return 0 if result.get("status") == "ok" else 1
        if args.command == "runner":
            if args.runner_command == "start":
                runner_start(args)
                return 0
            if args.runner_command == "once":
                print(json.dumps(runner_once(args), ensure_ascii=True))
                return 0
        if args.command == "chief":
            if args.chief_command == "start":
                print(json.dumps(chief_start(args), ensure_ascii=True))
                return 0
            if args.chief_command == "once":
                print(json.dumps(chief_once(args), ensure_ascii=True))
                return 0
    except (ValueError, OSError) as exc:
        parser.error(_with_orientation_hint(str(exc)))
        return 2

    try:
        asyncio.run(run_client_from_args(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
