from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from acp.hub.app import HubRuntime, create_app, create_runtime_from_env
from acp.hub.event_store import InMemoryEventStore
from acp.hub.migrations import apply_sqlite_migrations


def _msg_body(*, sender: str, recipient: str) -> dict[str, str]:
    return {
        "id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": "phase11",
    }


def _hello(name: str, *, token: str | None = None) -> str:
    payload = {"type": "HELLO", "role": "agent", "name": name}
    if token is not None:
        payload["token"] = token
    return json.dumps(payload)


def _msg_frame(*, sender: str, recipient: str) -> str:
    return json.dumps({"type": "MSG", **_msg_body(sender=sender, recipient=recipient)})


class _FailRoutedStore(InMemoryEventStore):
    def append(self, *, event_type: str, payload: dict[str, object]) -> None:
        if event_type == "routed":
            raise RuntimeError("forced routed persistence failure")
        super().append(event_type=event_type, payload=payload)


def test_runtime_parses_persistence_strict_flag_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")
    monkeypatch.setenv("ACP_PERSISTENCE_STRICT", "true")

    runtime = create_runtime_from_env()

    assert runtime.persistence_strict is True
    assert runtime.as_status_payload()["persistence_strict"] is True


def test_http_tolerates_routed_persistence_failure_when_strict_is_false(websocket_factory) -> None:
    runtime = HubRuntime(event_store=_FailRoutedStore(), persistence_strict=False)
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="agent_sender", recipient="agent_receiver"),
        )

    assert response.status_code == 200
    assert len(receiver.sent) == 1


def test_http_keeps_success_when_routed_persistence_failure_happens_after_delivery_in_strict_mode(
    websocket_factory,
) -> None:
    runtime = HubRuntime(event_store=_FailRoutedStore(), persistence_strict=True)
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="agent_sender", recipient="agent_receiver"),
        )

    assert response.status_code == 200
    assert len(receiver.sent) == 1
    errors = [event for event in runtime.trace_sink if event.get("event") == "ERROR"]
    assert errors and errors[-1]["reason_code"] == "PERSISTENCE_ROUTED_FAILED"


def test_ws_keeps_sender_clean_when_routed_persistence_failure_happens_after_delivery_in_strict_mode(
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    sender = websocket_factory(
        [
            _hello("agent_sender"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    receiver = websocket_factory()
    active_agents: dict[str, object] = {}

    from acp.hub.session_registry import SessionRegistry

    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
        event_store=_FailRoutedStore(),
        persistence_strict=True,
    )

    runtime_errors = [frame for frame in sender.sent if frame.get("action") == "ERROR"]
    assert runtime_errors == []
    assert len(receiver.sent) == 1
    errors = [event for event in trace_sink if event.get("event") == "ERROR"]
    assert errors and errors[-1]["reason_code"] == "PERSISTENCE_ROUTED_FAILED"


def test_http_accepts_previous_token_within_overlap_window(
    monkeypatch: pytest.MonkeyPatch,
    websocket_factory,
) -> None:
    overlap_until = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")
    monkeypatch.setenv("ACP_TOKEN", "new-token")
    monkeypatch.setenv("ACP_TOKEN_PREVIOUS", "old-token")
    monkeypatch.setenv("ACP_TOKEN_OVERLAP_UNTIL", overlap_until)

    runtime = create_runtime_from_env()
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="agent_sender", recipient="agent_receiver"),
            headers={"X-ACP-Token": "old-token"},
        )

    assert response.status_code == 200
    status = runtime.as_status_payload()
    assert status["token_rotation_active"] is True
    assert isinstance(status["token_overlap_until"], str)


def test_http_rejects_previous_token_after_overlap_window(
    monkeypatch: pytest.MonkeyPatch,
    websocket_factory,
) -> None:
    overlap_until = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")
    monkeypatch.setenv("ACP_TOKEN", "new-token")
    monkeypatch.setenv("ACP_TOKEN_PREVIOUS", "old-token")
    monkeypatch.setenv("ACP_TOKEN_OVERLAP_UNTIL", overlap_until)

    runtime = create_runtime_from_env()
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="agent_sender", recipient="agent_receiver"),
            headers={"X-ACP-Token": "old-token"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"
    assert runtime.as_status_payload()["token_rotation_active"] is False


def test_ws_accepts_previous_token_within_overlap_window(
    monkeypatch: pytest.MonkeyPatch,
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    overlap_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "memory")
    monkeypatch.setenv("ACP_TOKEN", "new-token")
    monkeypatch.setenv("ACP_TOKEN_PREVIOUS", "old-token")
    monkeypatch.setenv("ACP_TOKEN_OVERLAP_UNTIL", overlap_until)
    runtime = create_runtime_from_env()

    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )
    sender = websocket_factory(
        [
            _hello("agent_sender", token="old-token"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )

    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
        persistence_strict=runtime.persistence_strict,
    )

    assert len(receiver.sent) == 1


def test_runtime_rejects_partial_token_rotation_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_TOKEN", "new-token")
    monkeypatch.setenv("ACP_TOKEN_PREVIOUS", "old-token")

    with pytest.raises(RuntimeError, match="ACP_TOKEN_PREVIOUS requires ACP_TOKEN_OVERLAP_UNTIL"):
        create_runtime_from_env()


def test_runtime_rejects_rotation_when_primary_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACP_TOKEN", raising=False)
    monkeypatch.setenv("ACP_TOKEN_PREVIOUS", "old-token")
    monkeypatch.setenv(
        "ACP_TOKEN_OVERLAP_UNTIL",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    )

    with pytest.raises(RuntimeError, match="ACP_TOKEN_PREVIOUS requires ACP_TOKEN"):
        create_runtime_from_env()


def test_startup_fails_when_sqlite_schema_tables_are_drifted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "drifted.sqlite3"
    apply_sqlite_migrations(sqlite_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE acl_rules")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(db_path))

    with pytest.raises(RuntimeError, match="phase-6 migration bootstrap failed"):
        create_runtime_from_env()


def test_http_rejected_event_payload_remains_secret_safe_for_token_failures() -> None:
    runtime = HubRuntime(required_token="live-token", event_store=InMemoryEventStore())
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json={**_msg_body(sender="agent_sender", recipient="agent_receiver"), "token": "body-secret-token"},
            headers={"X-ACP-Token": "header-secret-token"},
        )

    assert response.status_code == 401
    persisted = [event.payload for event in runtime.event_store.snapshot()]
    payload_dump = json.dumps(persisted)
    assert "body-secret-token" not in payload_dump
    assert "header-secret-token" not in payload_dump
    assert "live-token" not in payload_dump


def test_ws_rejected_event_payload_remains_secret_safe_for_invalid_hello_token(
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    runtime = HubRuntime(required_token="live-token", event_store=InMemoryEventStore())
    sender = websocket_factory([_hello("agent_sender", token="hello-secret-token")])

    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    persisted = [event.payload for event in runtime.event_store.snapshot()]
    payload_dump = json.dumps(persisted)
    assert "hello-secret-token" not in payload_dump
    assert "live-token" not in payload_dump
