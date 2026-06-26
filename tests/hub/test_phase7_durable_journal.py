from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import HubRuntime, create_app, create_runtime_from_env
from acp.hub.event_store import InMemoryEventStore
from acp.hub.journal import append_received
from acp.hub.migrations import apply_sqlite_migrations
from acp.hub.sqlite_event_store import SqliteEventStore
from acp.hub.ws_ingress import run_ws_ingress


def _msg_body(*, sender: str, recipient: str, msg_id: str | None = None) -> dict[str, str]:
    return {
        "id": msg_id or str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": "hello",
    }


def _msg_frame(*, sender: str, recipient: str, msg_id: str | None = None) -> str:
    return json.dumps({"type": "MSG", **_msg_body(sender=sender, recipient=recipient, msg_id=msg_id)})


def _hello_frame(name: str) -> str:
    return json.dumps({"type": "HELLO", "role": "agent", "name": name})


class _FailReceivedStore:
    def append(self, *, event_type: str, payload: dict[str, object]) -> None:
        if event_type == "received":
            raise RuntimeError("forced received persistence failure")


class _FlakyDestination:
    def __init__(self) -> None:
        self._failed_once = False

    async def send_json(self, payload: dict[str, str]) -> None:
        if not self._failed_once:
            self._failed_once = True
            raise RuntimeError("destination disconnected")


def test_records_received_and_terminal_events_for_http_and_ws(run_ingress, websocket_factory) -> None:
    event_store = InMemoryEventStore()
    runtime = HubRuntime(event_store=event_store)
    http_receiver = websocket_factory()
    ws_receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="http-receiver-session",
        websocket=http_receiver,
        name="http_receiver",
    )
    assert runtime.registry.register_agent(
        session_id="ws-receiver-session",
        websocket=ws_receiver,
        name="ws_receiver",
    )

    http_msg_id = str(uuid4())
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="orchestrator_1", recipient="http_receiver", msg_id=http_msg_id),
        )
    assert response.status_code == 200

    ws_msg_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            _hello_frame("ws_sender"),
            _msg_frame(sender="ws_sender", recipient="ws_receiver", msg_id=ws_msg_id),
        ]
    )
    run_ingress(
        sender_socket,
        session_id="ws-sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        event_store=event_store,
    )

    by_msg_id: dict[str, list[dict[str, object]]] = {}
    for event in event_store.snapshot():
        msg_id = event.payload.get("msg_id")
        if isinstance(msg_id, str):
            by_msg_id.setdefault(msg_id, []).append(event.payload)

    http_events = by_msg_id[http_msg_id]
    assert [event["ingress"] for event in http_events] == ["http", "http"]
    assert {event["event_id"].split(":")[1] for event in http_events} == {"received", "routed"}

    ws_events = by_msg_id[ws_msg_id]
    assert [event["ingress"] for event in ws_events] == ["ws", "ws"]
    assert {event["event_id"].split(":")[1] for event in ws_events} == {"received", "routed"}


def test_records_rejected_and_delivery_failed_with_reason_codes(
    api_client,
    hub_runtime,
    hello_frame,
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    hub_runtime.event_store = InMemoryEventStore()

    missing_msg = _msg_body(sender="orchestrator_1", recipient="missing_agent", msg_id=str(uuid4()))
    missing_response = api_client.post("/send", json=missing_msg)
    assert missing_response.status_code == 404

    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_flaky", msg_id=str(uuid4())),
        ]
    )
    flaky_socket = _FlakyDestination()
    assert hub_runtime.registry.register_agent(
        session_id="flaky-session",
        websocket=flaky_socket,
        name="agent_flaky",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=hub_runtime.active_agents,
        trace_sink=trace_sink,
        session_registry=hub_runtime.registry,
        event_store=hub_runtime.event_store,
    )

    rejected = [
        event
        for event in hub_runtime.event_store.snapshot()
        if event.event_type == "rejected"
        and event.payload.get("msg_id") == missing_msg["id"]
    ]
    assert rejected and rejected[0].payload["reason_code"] == "DESTINATION_NOT_FOUND"

    delivery_failed = [
        event for event in hub_runtime.event_store.snapshot() if event.event_type == "delivery_failed"
    ]
    assert delivery_failed and delivery_failed[0].payload["reason_code"] == "DESTINATION_DELIVERY_FAILED"


def test_journal_events_are_immutable_and_payload_allowlisted_secret_safe(sqlite_db_path) -> None:
    apply_sqlite_migrations(sqlite_path=sqlite_db_path)
    store = SqliteEventStore(sqlite_path=sqlite_db_path)

    msg_id = str(uuid4())
    message = {
        "id": msg_id,
        "thread_id": str(uuid4()),
        "from": "agent_sender",
        "to": "agent_receiver",
        "action": "TASK",
        "payload": '{"token":"top-secret","Authorization":"Bearer abc"}',
    }
    append_received(event_store=store, ingress="http", message=message)
    append_received(event_store=store, ingress="http", message=message)

    events = store.events_for_msg(msg_id)
    assert len(events) == 1
    persisted = events[0].payload
    assert set(persisted.keys()) == {
        "action",
        "created_at",
        "event_id",
        "from",
        "ingress",
        "msg_id",
        "thread_id",
        "to",
    }
    assert "token" not in json.dumps(persisted)
    assert "Authorization" not in json.dumps(persisted)


def test_http_tolerant_default_received_persist_failure_returns_503(websocket_factory) -> None:
    runtime = HubRuntime(event_store=_FailReceivedStore())
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=websocket_factory(),
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    payload = _msg_body(sender="orchestrator_1", recipient="agent_receiver")
    with TestClient(app) as client:
        response = client.post("/send", json=payload)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "INVALID_FIELD"
    assert body["field"] == "id"


def test_ws_tolerant_default_received_persist_failure_emits_error_without_close(
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    sender_socket = websocket_factory(
        [
            _hello_frame("agent_sender"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}

    from acp.hub.session_registry import SessionRegistry

    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
        event_store=_FailReceivedStore(),
    )

    assert sender_socket.closed is False
    runtime_errors = [frame for frame in sender_socket.sent if frame.get("action") == "ERROR"]
    assert len(runtime_errors) == 1
    assert runtime_errors[0]["field"] == "id"
    assert receiver_socket.sent == []


def test_acknowledged_message_history_survives_runtime_restart(
    sqlite_runtime_factory,
    websocket_factory,
) -> None:
    runtime1 = sqlite_runtime_factory()
    receiver_socket = websocket_factory()
    assert runtime1.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    msg_id = str(uuid4())
    app = create_app(runtime=runtime1)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="orchestrator_1", recipient="agent_receiver", msg_id=msg_id),
        )
    assert response.status_code == 200

    runtime2 = sqlite_runtime_factory()
    store2 = runtime2.event_store
    assert isinstance(store2, SqliteEventStore)
    events = store2.events_for_msg(msg_id)
    assert {event.event_type for event in events} == {"received", "routed"}


def test_sqlite_event_store_uses_existing_rows_after_reinit(sqlite_db_path) -> None:
    apply_sqlite_migrations(sqlite_path=sqlite_db_path)
    store1 = SqliteEventStore(sqlite_path=sqlite_db_path)
    msg_id = str(uuid4())
    append_received(
        event_store=store1,
        ingress="http",
        message={
            "id": msg_id,
            "from": "agent_sender",
            "to": "agent_receiver",
            "action": "TASK",
            "thread_id": str(uuid4()),
        },
    )

    store2 = SqliteEventStore(sqlite_path=sqlite_db_path)
    events = store2.events_for_msg(msg_id)
    assert len(events) == 1
    assert events[0].payload["msg_id"] == msg_id


def test_create_runtime_from_env_uses_sqlite_event_store_when_backend_sqlite(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "phase7-runtime.sqlite3"
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(db_path))

    runtime = create_runtime_from_env()

    assert isinstance(runtime.event_store, SqliteEventStore)
    assert runtime.storage_ready is True
    # The sqlite backend persists coordination sessions across restarts, so the
    # runtime advertises itself as coordination-durable for ops/monitoring.
    assert runtime.as_status_payload()["coordination_durable"] is True


def test_create_runtime_from_env_defaults_to_sqlite_when_backend_unset(
    monkeypatch,
    tmp_path,
) -> None:
    # C-REL-01: a self-hoster who runs ACP without setting any env var must NOT
    # silently land on the memory backend (which wipes state on restart). The
    # safe out-of-the-box default is sqlite.
    db_path = tmp_path / "default-runtime.sqlite3"
    monkeypatch.delenv("ACP_PERSISTENCE_BACKEND", raising=False)
    monkeypatch.setenv("ACP_SQLITE_PATH", str(db_path))

    runtime = create_runtime_from_env()

    assert isinstance(runtime.event_store, SqliteEventStore)
    assert runtime.storage_ready is True
    assert runtime.as_status_payload()["coordination_durable"] is True


def test_create_runtime_from_env_memory_backend_is_not_coordination_durable(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")

    runtime = create_runtime_from_env()

    # Memory backend wipes every session/member on restart; /runtime must make
    # that observable so a redeploy footgun does not stay silent.
    assert runtime.as_status_payload()["coordination_durable"] is False


def test_create_runtime_from_env_memory_backend_emits_warning_and_flag(
    monkeypatch,
    caplog,
) -> None:
    # C-REL-02: choosing memory on purpose must be LOUD. A redeploy wipes all
    # state, so the boot logs a WARNING and /runtime advertises the footgun.
    import logging

    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")

    with caplog.at_level(logging.WARNING, logger="acp.hub"):
        runtime = create_runtime_from_env()

    assert runtime.as_status_payload()["memory_backend_warning"] is True
    assert any(
        record.levelno == logging.WARNING and "memory" in record.getMessage().lower()
        for record in caplog.records
    )


def test_create_runtime_from_env_sqlite_backend_has_no_memory_warning(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "no-warn.sqlite3"))

    runtime = create_runtime_from_env()

    assert runtime.as_status_payload()["memory_backend_warning"] is False
