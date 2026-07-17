from __future__ import annotations

import json
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))

from claude_code_cli_adapter import ClaudeCodeCliAdapter  # noqa: E402
from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBinding,
    HostBridge,
    HostCredential,
    HostDelivery,
    HostDeliveryError,
    JsonBridgeStore,
)


SESSION_ID = "claude-session-existing"


def _delivery() -> HostDelivery:
    return HostDelivery(
        message_id="msg-claude-1",
        correlation_id="msg-claude-1",
        sender="chief",
        instructions="Inspect the change",
    )


def _response() -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": "msg-claude-1",
            "session_id": "acp-session",
            "from": "chief",
            "to": "worker",
            "action": "TASK",
            "payload": json.dumps({"instructions": "Inspect the change"}),
        },
        "delivery": {"ack_required": True, "message_id": "msg-claude-1", "receipt_handle": "receipt-1"},
    }


def _stream(*events: dict[str, Any]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _result(*, session_id: str = SESSION_ID, text: str = "Claude completed safely") -> str:
    return _stream(
        {"type": "system", "subtype": "init", "session_id": session_id},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "partial secret"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": session_id, "result": text},
    )


class FakeRunner:
    def __init__(self, *results: subprocess.CompletedProcess[str] | BaseException) -> None:
        self.results = deque(results)
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result


def _completed(stdout: str, *, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr="host internal token")


def _binding(**extra: str) -> HostBinding:
    return HostBinding(
        adapter_id="claude_code_cli",
        values={"executable": r"C:\\Tools\\claude.exe", "session_id": SESSION_ID, **extra},
    )


def test_claude_cli_resumes_exact_existing_session_and_uses_terminal_result() -> None:
    runner = FakeRunner(_completed('{"loggedIn":true}\n'), _completed(_result()))
    adapter = ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner)

    result = adapter.deliver(_binding(), _delivery())

    assert result.summary == "Claude completed safely"
    assert runner.calls[0][0] == [r"C:\\Tools\\claude.exe", "auth", "status"]
    assert runner.calls[1][0] == [
        r"C:\\Tools\\claude.exe",
        "-p",
        "--resume",
        SESSION_ID,
        "--output-format",
        "stream-json",
        "--verbose",
        "Inspect the change",
    ]


def test_claude_cli_idle_bridge_never_invokes_auth_or_model(tmp_path: Path) -> None:
    runner = FakeRunner()
    registry = AdapterRegistry()
    registry.register(ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner))
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )

    for _ in range(3):
        assert bridge.handle({"status": "timeout"}, acknowledge=lambda _: None, reply=lambda *_: None) == {"status": "idle"}

    assert runner.calls == []


def test_claude_cli_reconcile_fails_closed_without_second_prompt() -> None:
    runner = FakeRunner()
    adapter = ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="refusing duplicate"):
        adapter.reconcile(_binding(), _delivery())

    assert runner.calls == []


def test_claude_cli_rejects_auth_absent_without_model_invocation() -> None:
    runner = FakeRunner(_completed('{"loggedIn":false,"authMethod":"none"}\n'))
    adapter = ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="authentication is unavailable"):
        adapter.deliver(_binding(), _delivery())

    assert len(runner.calls) == 1


def test_claude_cli_rejects_wrong_terminal_session_without_ack(tmp_path: Path) -> None:
    runner = FakeRunner(_completed('{"loggedIn":true}\n'), _completed(_result(session_id="other-session")))
    registry = AdapterRegistry()
    registry.register(ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner))
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []

    with pytest.raises(HostDeliveryError, match="different session"):
        bridge.handle(_response(), acknowledge=lambda _: acknowledgments.append("ack"), reply=lambda *_: None)

    assert acknowledgments == []


def test_claude_cli_ignores_partial_events_and_requires_result() -> None:
    runner = FakeRunner(
        _completed('{"loggedIn":true}\n'),
        _completed(_stream({"type": "assistant", "message": {"content": [{"type": "text", "text": "partial"}]}})),
    )
    adapter = ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="terminal result"):
        adapter.deliver(_binding(), _delivery())


def test_claude_cli_timeout_is_safe_and_sanitized() -> None:
    timeout = subprocess.TimeoutExpired(cmd=["claude"], timeout=1, output="internal token", stderr="internal token")
    runner = FakeRunner(_completed('{"loggedIn":true}\n'), timeout)
    adapter = ClaudeCodeCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="completion deadline"):
        adapter.deliver(_binding(), _delivery())


def test_claude_cli_bearer_credential_ref_is_only_in_child_environment(tmp_path: Path) -> None:
    secret = "test-secret"
    runner = FakeRunner(_completed(_result()))
    adapter = ClaudeCodeCliAdapter(
        request_timeout_seconds=1,
        runner=runner,
        credential_resolver=lambda ref: HostCredential(bearer_token=secret) if ref == "env:CLAUDE" else None,
    )
    binding = _binding(credential_ref="env:CLAUDE")
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=binding,
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )

    bridge.handle(_response(), acknowledge=lambda _: None, reply=lambda *_: None)

    assert len(runner.calls) == 1
    assert runner.calls[0][1]["env"]["ANTHROPIC_API_KEY"] == secret
    assert secret not in (tmp_path / "state.json").read_text(encoding="utf-8")
