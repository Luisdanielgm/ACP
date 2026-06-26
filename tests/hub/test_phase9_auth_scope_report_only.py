from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import create_app
from acp.hub.sqlite_event_store import SqliteEventStore


def _insert_principal(db_path, *, principal_name: str, scopes: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO auth_principals(principal_id, principal_name, scopes_csv)
            VALUES (?, ?, ?)
            """,
            (str(uuid4()), principal_name, ",".join(scopes)),
        )
        conn.commit()
    finally:
        conn.close()


def _msg_body(*, sender: str, recipient: str) -> dict[str, str]:
    return {
        "id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": "hello",
    }


def _hello(name: str, *, role: str = "agent") -> str:
    return json.dumps({"type": "HELLO", "role": role, "name": name})


def _msg_frame(*, sender: str, recipient: str) -> str:
    return json.dumps({"type": "MSG", **_msg_body(sender=sender, recipient=recipient)})


def test_shared_auth_path_emits_allow_trace_for_http_send(
    sqlite_runtime_factory,
    sqlite_db_path,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="orchestrator_1", scopes=["send"])

    runtime = sqlite_runtime_factory()
    receiver_socket = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
        )

    assert response.status_code == 200
    authz = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ"]
    assert authz
    send_scope = [
        event
        for event in authz
        if event.get("scope") == "send"
        and event.get("surface") == "http_send"
        and event.get("reason_code") == "SCOPE_GRANTED"
    ]
    assert send_scope and send_scope[-1]["decision"] == "allow"


def test_ws_send_scope_missing_is_report_only_would_deny_but_message_routes(
    sqlite_runtime_factory,
    sqlite_db_path,
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["connect"])
    _insert_principal(sqlite_db_path, principal_name="agent_receiver", scopes=["connect", "send"])

    runtime = sqlite_runtime_factory()
    receiver_socket = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    sender_socket = websocket_factory(
        [
            _hello("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    assert len(receiver_socket.sent) == 1
    authz_events = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ"]
    connect = [event for event in authz_events if event.get("scope") == "connect"]
    send = [event for event in authz_events if event.get("scope") == "send"]
    assert connect and connect[-1]["decision"] == "allow"
    assert send and send[-1]["decision"] == "would_deny"


def test_ws_observer_without_scope_still_connects_with_would_deny_trace(
    sqlite_runtime_factory,
    run_ingress,
    websocket_factory,
) -> None:
    runtime = sqlite_runtime_factory()
    observer_socket = websocket_factory([_hello("observer_live", role="observer")])
    run_ingress(
        observer_socket,
        session_id="observer-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    # Observer still receives SNAPSHOT in report-only mode.
    assert observer_socket.sent and observer_socket.sent[0]["type"] == "SNAPSHOT"
    authz = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ"]
    assert authz
    assert authz[-1]["scope"] == "observe"
    assert authz[-1]["decision"] == "would_deny"


def test_http_replay_scope_trace_report_only_for_missing_and_known_principal(
    sqlite_runtime_factory,
    sqlite_db_path,
) -> None:
    runtime = sqlite_runtime_factory()
    store = runtime.event_store
    assert isinstance(store, SqliteEventStore)
    store.append(
        event_type="received",
        payload={
            "event_id": "evt-replay-1",
            "created_at": "2026-03-05T10:00:00.000000Z",
            "msg_id": str(uuid4()),
            "thread_id": str(uuid4()),
            "from": "agent_a",
            "to": "agent_b",
            "action": "TASK",
            "ingress": "http",
        },
    )
    _insert_principal(sqlite_db_path, principal_name="observer_live", scopes=["replay"])

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        no_principal = client.get("/replay/events")
        assert no_principal.status_code == 200

        with_principal = client.get(
            "/replay/events",
            headers={"X-ACP-Principal": "observer_live"},
        )
        assert with_principal.status_code == 200

    authz = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ" and event.get("scope") == "replay"]
    assert len(authz) >= 2
    assert authz[-2]["decision"] == "would_deny"
    assert authz[-1]["decision"] == "allow"
