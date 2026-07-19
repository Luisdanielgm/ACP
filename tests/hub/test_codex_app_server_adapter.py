from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))

from codex_app_server_adapter import CodexAppServerAdapter  # noqa: E402
from codex_app_server_stdio_adapter import CodexAppServerStdioAdapter  # noqa: E402
from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBinding,
    HostBindingError,
    HostBridge,
    HostCredential,
    HostDelivery,
    HostDeliveryError,
    JsonBridgeStore,
    binding_lock_fingerprint,
)
from config_reservation import reserve_config  # noqa: E402


THREAD_ID = "019f58d8-b3e2-7570-a416-4d2ee9140e90"


def _delivery() -> HostDelivery:
    return HostDelivery(
        message_id="msg-1",
        correlation_id="msg-1",
        sender="chief",
        instructions="Inspect the change",
    )


def _response() -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": "msg-1",
            "session_id": "acp-session",
            "from": "chief",
            "to": "worker",
            "action": "TASK",
            "payload": json.dumps({"instructions": "Inspect the change"}),
        },
        "delivery": {
            "ack_required": True,
            "message_id": "msg-1",
            "receipt_handle": "receipt-1",
        },
    }


class FakeCodexConnection:
    def __init__(
        self,
        *,
        turns: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
        reject_resume: bool = False,
        disconnect_after_start: bool = False,
    ) -> None:
        self.turns = turns or []
        self.events = events or []
        self.reject_resume = reject_resume
        self.disconnect_after_start = disconnect_after_start
        self.sent: list[dict[str, Any]] = []
        self.pending: deque[dict[str, Any]] = deque()
        self.started_turns = 0

    def __enter__(self) -> "FakeCodexConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        method = message.get("method")
        if method == "initialize":
            self.pending.append({"id": message["id"], "result": {"userAgent": "codex/test"}})
        elif method == "thread/resume":
            if self.reject_resume:
                self.pending.append({"id": message["id"], "error": {"code": -32000, "message": "not found"}})
            else:
                self.pending.append(
                    {
                        "id": message["id"],
                        "result": {"thread": {"id": THREAD_ID, "turns": self.turns}},
                    }
                )
        elif method == "turn/start":
            self.started_turns += 1
            self.pending.append(
                {
                    "id": message["id"],
                    "result": {"turn": {"id": "turn-1", "status": "inProgress", "items": []}},
                }
            )
            self.pending.extend(self.events)
        elif method == "turn/interrupt":
            self.pending.append({"id": message["id"], "result": {}})

    def recv(self, timeout: float | None = None) -> str:
        if self.pending:
            return json.dumps(self.pending.popleft())
        if self.disconnect_after_start and self.started_turns:
            raise OSError("disconnected with internal secret")
        raise TimeoutError("fake receive timeout")


class FakeConnect:
    def __init__(self, *connections: FakeCodexConnection) -> None:
        self.connections = deque(connections)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, endpoint: str, **kwargs: Any) -> FakeCodexConnection:
        self.calls.append({"endpoint": endpoint, **kwargs})
        return self.connections.popleft()


def _binding() -> HostBinding:
    return HostBinding(
        adapter_id="codex_app_server",
        values={"endpoint": "ws://127.0.0.1:4500", "thread_id": THREAD_ID},
    )


def _stdio_binding() -> HostBinding:
    return HostBinding(
        adapter_id="codex_app_server_stdio",
        values={"executable": "C:/tools/codex.exe", "thread_id": THREAD_ID},
    )


def _success_events(*, secret: str = "must-not-leak") -> list[dict[str, Any]]:
    return [
        {"method": "configWarning", "params": {"details": secret}},
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": THREAD_ID, "turnId": "turn-1", "itemId": "item-1", "delta": "partial"},
        },
        {
            "method": "item/completed",
            "params": {
                "threadId": THREAD_ID,
                "turnId": "turn-1",
                "completedAtMs": 1,
                "item": {"id": "item-1", "type": "agentMessage", "text": "Finished safely", "phase": "final_answer"},
            },
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": THREAD_ID,
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            },
        },
    ]


def test_codex_adapter_resumes_same_thread_and_starts_exactly_one_turn() -> None:
    connection = FakeCodexConnection(events=_success_events())
    connect = FakeConnect(connection)
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=connect)

    result = adapter.deliver(_binding(), _delivery())

    assert result.summary == "Finished safely"
    assert [message["method"] for message in connection.sent] == [
        "initialize",
        "initialized",
        "thread/resume",
        "turn/start",
    ]
    assert connection.sent[-2]["params"] == {"threadId": THREAD_ID}
    assert connection.sent[-1]["params"] == {
        "threadId": THREAD_ID,
        "clientUserMessageId": _delivery().host_message_id(),
        "input": [{"type": "text", "text": "Inspect the change"}],
    }


def test_codex_stdio_adapter_starts_only_after_delivery_and_resumes_same_thread() -> None:
    connection = FakeCodexConnection(events=_success_events())
    started: list[str] = []
    adapter = CodexAppServerStdioAdapter(
        request_timeout_seconds=1,
        connection_factory=lambda executable: started.append(executable) or connection,
    )

    result = adapter.deliver(_stdio_binding(), _delivery())

    assert result.summary == "Finished safely"
    assert started == ["C:/tools/codex.exe"]
    assert [message["method"] for message in connection.sent] == [
        "initialize",
        "initialized",
        "thread/resume",
        "turn/start",
    ]


def test_codex_stdio_adapter_rejects_loopback_endpoint() -> None:
    adapter = CodexAppServerStdioAdapter(connection_factory=lambda _executable: FakeCodexConnection())
    with pytest.raises(HostBindingError, match="does not accept an endpoint"):
        adapter.deliver(
            HostBinding(
                adapter_id="codex_app_server_stdio",
                values={"executable": "C:/tools/codex.exe", "thread_id": THREAD_ID, "endpoint": "ws://127.0.0.1:4500"},
            ),
            _delivery(),
        )


def test_codex_adapter_ignores_partial_events_until_terminal_completion() -> None:
    connection = FakeCodexConnection(
        events=[
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": THREAD_ID, "turnId": "turn-1", "itemId": "item-1", "delta": "partial"},
            }
        ]
    )
    adapter = CodexAppServerAdapter(request_timeout_seconds=0.02, connect=FakeConnect(connection))

    with pytest.raises(HostDeliveryError, match="completion deadline"):
        adapter.deliver(_binding(), _delivery())

    assert "turn/interrupt" in [message["method"] for message in connection.sent]


def test_codex_bindings_share_endpoint_lock_scope_but_not_delivery_identity() -> None:
    first = _binding()
    second = HostBinding(
        adapter_id="codex_app_server",
        values={"endpoint": "ws://127.0.0.1:4500", "thread_id": "thread-2"},
    )

    assert first.fingerprint() != second.fingerprint()
    assert binding_lock_fingerprint(first, scope="endpoint") == binding_lock_fingerprint(second, scope="endpoint")


def test_codex_loopback_aliases_share_endpoint_lock_scope() -> None:
    first = _binding()
    second = HostBinding(
        adapter_id="codex_app_server",
        values={"endpoint": "ws://localhost:4500", "thread_id": "thread-2"},
    )

    assert binding_lock_fingerprint(first, scope="endpoint") == binding_lock_fingerprint(second, scope="endpoint")


def test_codex_bindings_on_different_endpoints_have_isolated_lock_scope() -> None:
    first = _binding()
    second = HostBinding(
        adapter_id="codex_app_server",
        values={"endpoint": "ws://127.0.0.1:4501", "thread_id": THREAD_ID},
    )

    assert binding_lock_fingerprint(first, scope="endpoint") != binding_lock_fingerprint(second, scope="endpoint")


def test_shared_codex_endpoint_reservation_rejects_second_bridge(tmp_path: Path) -> None:
    lock_target = tmp_path / f"{binding_lock_fingerprint(_binding(), scope='endpoint')}.runtime"
    with reserve_config(lock_target):
        with pytest.raises(ValueError, match="reserved by another process"):
            with reserve_config(lock_target):
                pass

def test_codex_adapter_interrupts_an_accepted_turn_after_protocol_error() -> None:
    connection = FakeCodexConnection(events=["not a Codex protocol message"])
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(connection))

    with pytest.raises(HostDeliveryError, match="invalid message"):
        adapter.deliver(_binding(), _delivery())

    assert "turn/interrupt" in [message["method"] for message in connection.sent]


def test_codex_adapter_rejects_unknown_thread_without_starting_or_acking(tmp_path: Path) -> None:
    connection = FakeCodexConnection(reject_resume=True)
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(connection))
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []

    with pytest.raises(HostDeliveryError, match="thread/resume"):
        bridge.handle(_response(), acknowledge=lambda _: acknowledgments.append("ack"), reply=lambda *_: None)

    assert connection.started_turns == 0
    assert acknowledgments == []


def test_codex_retry_without_visible_client_id_fails_closed_without_duplicate_turn(tmp_path: Path) -> None:
    first_connection = FakeCodexConnection(disconnect_after_start=True)
    first_adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(first_connection))
    registry = AdapterRegistry()
    registry.register(first_adapter)
    state_path = tmp_path / "state.json"
    first = HostBridge(registry=registry, binding=_binding(), store=JsonBridgeStore(state_path), allowed_senders=("chief",))

    with pytest.raises(HostDeliveryError):
        first.handle(_response(), acknowledge=lambda _: None, reply=lambda *_: None)

    first_record = next(iter(json.loads(state_path.read_text(encoding="utf-8"))["deliveries"].values()))
    assert first_record["status"] == "received"
    assert not first_record.get("replied")
    assert not first_record.get("acked")

    retry_connection = FakeCodexConnection(turns=[])
    retry_adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(retry_connection))
    retry_registry = AdapterRegistry()
    retry_registry.register(retry_adapter)
    restarted = HostBridge(
        registry=retry_registry,
        binding=_binding(),
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )

    with pytest.raises(HostDeliveryError, match="refusing duplicate"):
        restarted.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("ambiguous delivery must not ACK"),
            reply=lambda *_: pytest.fail("ambiguous delivery must not REPLY"),
        )

    assert first_connection.started_turns == 1
    assert retry_connection.started_turns == 0


def test_codex_reconcile_recovers_completed_turn_without_new_start() -> None:
    message_id = _delivery().host_message_id()
    turns = [
        {
            "id": "turn-existing",
            "status": "completed",
            "items": [
                {
                    "id": "user-1",
                    "type": "userMessage",
                    "clientId": message_id,
                    "content": [{"type": "text", "text": "Inspect the change"}],
                },
                {"id": "agent-1", "type": "agentMessage", "text": "Recovered result", "phase": "final_answer"},
            ],
        }
    ]
    connection = FakeCodexConnection(turns=turns)
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(connection))

    result = adapter.reconcile(_binding(), _delivery())

    assert result.summary == "Recovered result"
    assert connection.started_turns == 0


def test_codex_idle_bridge_makes_zero_app_server_connections(tmp_path: Path) -> None:
    connect = FakeConnect()
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=connect)
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(tmp_path / "state.json"),
        allowed_senders=("chief",),
    )

    for _ in range(3):
        assert bridge.handle({"status": "timeout"}, acknowledge=lambda _: None, reply=lambda *_: None) == {"status": "idle"}

    assert connect.calls == []


def test_codex_internal_events_and_connection_errors_are_not_persisted_or_replied(tmp_path: Path) -> None:
    secret = "internal-secret-value"
    connection = FakeCodexConnection(events=_success_events(secret=secret))
    adapter = CodexAppServerAdapter(request_timeout_seconds=1, connect=FakeConnect(connection))
    registry = AdapterRegistry()
    registry.register(adapter)
    state_path = tmp_path / "state.json"
    summaries: list[str] = []
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )

    bridge.handle(_response(), acknowledge=lambda _: None, reply=lambda _d, result, _id: summaries.append(result.summary))

    assert summaries == ["Finished safely"]
    assert secret not in state_path.read_text(encoding="utf-8")


def test_codex_credential_ref_adds_bearer_only_to_websocket_handshake() -> None:
    secret = "handshake-secret"
    connection = FakeCodexConnection(events=_success_events())
    connect = FakeConnect(connection)
    adapter = CodexAppServerAdapter(
        request_timeout_seconds=1,
        connect=connect,
        credential_resolver=lambda ref: HostCredential(bearer_token=secret) if ref == "env:CODEX" else None,
    )
    binding = HostBinding(
        adapter_id="codex_app_server",
        values={
            "endpoint": "ws://127.0.0.1:4500",
            "thread_id": THREAD_ID,
            "credential_ref": "env:CODEX",
        },
    )

    assert adapter.deliver(binding, _delivery()).summary == "Finished safely"
    assert connect.calls[0]["additional_headers"] == {"Authorization": f"Bearer {secret}"}
    assert secret not in json.dumps(binding.safe_descriptor())


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:4500", "ws://host.example:4500"])
def test_codex_binding_rejects_non_websocket_or_non_loopback_endpoint(endpoint: str) -> None:
    adapter = CodexAppServerAdapter(connect=FakeConnect())
    binding = HostBinding(adapter_id="codex_app_server", values={"endpoint": endpoint, "thread_id": THREAD_ID})

    with pytest.raises(HostBindingError):
        adapter.deliver(binding, _delivery())
