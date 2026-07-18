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

from codex_cli_adapter import CodexCliAdapter  # noqa: E402
from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBinding,
    HostBindingError,
    HostBridge,
    HostCredential,
    HostDelivery,
    HostDeliveryError,
    JsonBridgeStore,
)


SESSION_ID = "019f58d8-b3e2-7570-a416-4d2ee9140e90"


def _delivery() -> HostDelivery:
    return HostDelivery(
        message_id="msg-codex-1",
        correlation_id="msg-codex-1",
        sender="chief",
        instructions="Inspect the change",
    )


def _response() -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": "msg-codex-1",
            "session_id": "acp-session",
            "from": "chief",
            "to": "worker",
            "action": "TASK",
            "payload": json.dumps({"instructions": "Inspect the change"}),
        },
        "delivery": {"ack_required": True, "message_id": "msg-codex-1", "receipt_handle": "receipt-1"},
    }


def _stream(*events: dict[str, Any]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _result(*, session_id: str = SESSION_ID, text: str = "Codex finished safely") -> str:
    return _stream(
        {"type": "thread.started", "thread_id": session_id},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item-1", "type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}},
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
        adapter_id="codex_cli",
        values={"executable": r"C:\\Tools\\codex.exe", "session_id": SESSION_ID, **extra},
    )


def test_codex_cli_resumes_exact_existing_session_and_uses_terminal_result() -> None:
    runner = FakeRunner(_completed(_result()))
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    result = adapter.deliver(_binding(), _delivery())

    assert result.summary == "Codex finished safely"
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == [
        r"C:\\Tools\\codex.exe",
        "exec",
        "resume",
        SESSION_ID,
        "--json",
        "Inspect the change",
    ]


def test_codex_cli_idle_bridge_never_spawns_process(tmp_path: Path) -> None:
    runner = FakeRunner()
    registry = AdapterRegistry()
    registry.register(CodexCliAdapter(request_timeout_seconds=1, runner=runner))
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )

    for _ in range(3):
        assert bridge.handle({"status": "timeout"}, acknowledge=lambda _: None, reply=lambda *_: None) == {"status": "idle"}

    assert runner.calls == []


def test_codex_cli_reconcile_fails_closed_without_second_prompt() -> None:
    runner = FakeRunner()
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="refusing duplicate"):
        adapter.reconcile(_binding(), _delivery())

    assert runner.calls == []


def test_codex_cli_rejects_resumed_wrong_session_without_ack(tmp_path: Path) -> None:
    runner = FakeRunner(_completed(_result(session_id="other-session")))
    registry = AdapterRegistry()
    registry.register(CodexCliAdapter(request_timeout_seconds=1, runner=runner))
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


def test_codex_cli_requires_terminal_turn_completed() -> None:
    runner = FakeRunner(
        _completed(
            _stream(
                {"type": "thread.started", "thread_id": SESSION_ID},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "partial"}},
            )
        )
    )
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="terminal result"):
        adapter.deliver(_binding(), _delivery())


def test_codex_cli_turn_failed_is_reported_as_failure() -> None:
    runner = FakeRunner(
        _completed(
            _stream(
                {"type": "thread.started", "thread_id": SESSION_ID},
                {"type": "turn.failed", "error": {"message": "boom"}},
            )
        )
    )
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="did not complete successfully"):
        adapter.deliver(_binding(), _delivery())


def test_codex_cli_non_zero_exit_is_a_terminal_error() -> None:
    runner = FakeRunner(_completed("", code=1))
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="terminal result"):
        adapter.deliver(_binding(), _delivery())


def test_codex_cli_timeout_is_safe_and_sanitized() -> None:
    timeout = subprocess.TimeoutExpired(cmd=["codex"], timeout=1, output="internal token", stderr="internal token")
    runner = FakeRunner(timeout)
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=runner)

    with pytest.raises(HostDeliveryError, match="completion deadline"):
        adapter.deliver(_binding(), _delivery())


def test_codex_cli_deduplicates_repeated_task_delivery(tmp_path: Path) -> None:
    runner = FakeRunner(_completed(_result()))
    registry = AdapterRegistry()
    registry.register(CodexCliAdapter(request_timeout_seconds=1, runner=runner))
    state_path = tmp_path / "state.json"
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )

    first = bridge.handle(_response(), acknowledge=lambda _: None, reply=lambda *_: None)
    second = bridge.handle(_response(), acknowledge=lambda _: None, reply=lambda *_: None)

    assert first["status"] == "completed"
    assert second["status"] == "duplicate"
    assert len(runner.calls) == 1


def test_codex_cli_bearer_credential_ref_is_only_in_child_environment(tmp_path: Path) -> None:
    secret = "test-secret"
    runner = FakeRunner(_completed(_result()))
    adapter = CodexCliAdapter(
        request_timeout_seconds=1,
        runner=runner,
        credential_resolver=lambda ref: HostCredential(bearer_token=secret) if ref == "env:CODEX" else None,
    )
    binding = _binding(credential_ref="env:CODEX")
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
    assert runner.calls[0][1]["env"]["OPENAI_API_KEY"] == secret
    assert secret not in (tmp_path / "state.json").read_text(encoding="utf-8")


def test_codex_cli_binding_requires_absolute_executable() -> None:
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=FakeRunner())
    binding = HostBinding(adapter_id="codex_cli", values={"executable": "codex.exe", "session_id": SESSION_ID})

    with pytest.raises(HostBindingError, match="absolute path"):
        adapter.deliver(binding, _delivery())


def test_codex_cli_binding_requires_absolute_directory() -> None:
    adapter = CodexCliAdapter(request_timeout_seconds=1, runner=FakeRunner())
    binding = _binding(directory="relative/dir")

    with pytest.raises(HostBindingError, match="absolute path"):
        adapter.deliver(binding, _delivery())
