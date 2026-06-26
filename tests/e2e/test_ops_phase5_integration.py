from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import datetime, timezone
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.hub.app import HubRuntime, create_app

HOST = "127.0.0.1"


def _load_acp_module() -> object:
    path = Path("ACP_AGENT/acp.py")
    spec = importlib.util.spec_from_file_location("acp_single_file", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ACP_AGENT/acp.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["acp_single_file"] = module
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


class LiveHub:
    def __init__(self, port: int) -> None:
        self.port = port
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{HOST}:{self.port}/ws"

    def start(self) -> None:
        runtime = HubRuntime()
        app = create_app(runtime=runtime)
        config = uvicorn.Config(app, host=HOST, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        self._wait_ready()

    def stop(self) -> None:
        if self._server is None or self._thread is None:
            return
        self._server.should_exit = True
        self._thread.join(timeout=10)
        self._server = None
        self._thread = None

    def _wait_ready(self, timeout_seconds: float = 10.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if _http_get_json(self.base_url + "/health").get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.05)
        raise AssertionError("hub readiness timeout")


def _http_get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _http_post_send(base_url: str, body: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(body)
    enriched.setdefault("type", "MSG")
    enriched.setdefault("id", str(uuid4()))
    enriched.setdefault("ts", _utc_now_rfc3339())

    req = urllib.request.Request(
        base_url + "/send",
        data=json.dumps(enriched).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


async def _wait_until(predicate: Any, *, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition timeout")


def _inbox_has_payload(inbox_dir: Path, needle: str) -> bool:
    if not inbox_dir.exists():
        return False
    for path in inbox_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("payload") == needle:
            return True
    return False


async def _run_clients(acp_module: Any, hub: LiveHub, *, root: Path) -> tuple[Any, Any, asyncio.Task[Any], asyncio.Task[Any]]:
    runtime_a = acp_module.ACPClientRuntime(
        agent_name="agent-a",
        hub_ws=hub.ws_url,
        inbox_dir=root / "inbox" / "agent-a",
        outbox_dir=root / "outbox" / "agent-a",
        sent_dir=root / "sent" / "agent-a",
        poll_ms=100,
    )
    runtime_b = acp_module.ACPClientRuntime(
        agent_name="agent-b",
        hub_ws=hub.ws_url,
        inbox_dir=root / "inbox" / "agent-b",
        outbox_dir=root / "outbox" / "agent-b",
        sent_dir=root / "sent" / "agent-b",
        poll_ms=100,
    )
    task_a = asyncio.create_task(runtime_a.run())
    task_b = asyncio.create_task(runtime_b.run())

    await _wait_until(
        lambda: set(_http_get_json(hub.base_url + "/agents").get("agents", [])) == {"agent-a", "agent-b"}
    )
    return runtime_a, runtime_b, task_a, task_b


async def _stop_clients(runtime_a: Any, runtime_b: Any, task_a: asyncio.Task[Any], task_b: asyncio.Task[Any]) -> None:
    runtime_a.stop()
    runtime_b.stop()
    await asyncio.wait_for(asyncio.gather(task_a, task_b, return_exceptions=True), timeout=10)


def test_task_reply_flow_live_hub_and_two_clients(tmp_path: Path) -> None:
    acp_module = _load_acp_module()
    hub = LiveHub(_free_port())
    hub.start()

    async def scenario() -> None:
        runtime_a, runtime_b, task_a, task_b = await _run_clients(acp_module, hub, root=tmp_path)
        try:
            response = _http_post_send(
                hub.base_url,
                {
                    "from": "orchestrator",
                    "to": "agent-b",
                    "action": "TASK",
                    "payload": "Implement login endpoint",
                },
            )
            assert response.get("status") == "ok"

            inbox_b = tmp_path / "inbox" / "agent-b"
            await _wait_until(lambda: _inbox_has_payload(inbox_b, "Implement login endpoint"), timeout_seconds=10)

            outbox_b = tmp_path / "outbox" / "agent-b"
            acp_module.enqueue_outbound_message(
                outbox_b,
                {"to": "agent-a", "action": "REPLY", "payload": "Login endpoint done"},
            )

            inbox_a = tmp_path / "inbox" / "agent-a"
            sent_b = tmp_path / "sent" / "agent-b"
            await _wait_until(lambda: _inbox_has_payload(inbox_a, "Login endpoint done"), timeout_seconds=10)
            await _wait_until(lambda: any(sent_b.glob("*.json")), timeout_seconds=10)
        finally:
            await _stop_clients(runtime_a, runtime_b, task_a, task_b)

    try:
        asyncio.run(scenario())
    finally:
        hub.stop()


def test_restart_recovery_reconnects_clients(tmp_path: Path) -> None:
    acp_module = _load_acp_module()
    hub = LiveHub(_free_port())
    hub.start()

    async def scenario() -> None:
        runtime_a, runtime_b, task_a, task_b = await _run_clients(acp_module, hub, root=tmp_path)
        try:
            hub.stop()
            await asyncio.sleep(0.3)
            hub.start()

            await _wait_until(
                lambda: set(_http_get_json(hub.base_url + "/agents").get("agents", [])) == {"agent-a", "agent-b"},
                timeout_seconds=20,
            )

            response = _http_post_send(
                hub.base_url,
                {
                    "from": "orchestrator",
                    "to": "agent-b",
                    "action": "TASK",
                    "payload": "Task after restart",
                },
            )
            assert response.get("status") == "ok"

            inbox_b = tmp_path / "inbox" / "agent-b"
            await _wait_until(lambda: _inbox_has_payload(inbox_b, "Task after restart"), timeout_seconds=12)
        finally:
            await _stop_clients(runtime_a, runtime_b, task_a, task_b)

    try:
        asyncio.run(scenario())
    finally:
        hub.stop()
