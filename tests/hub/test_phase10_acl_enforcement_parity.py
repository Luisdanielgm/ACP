from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import HubRuntime, create_app
from acp.hub.migrations import apply_sqlite_migrations
from acp.hub.sqlite_event_store import SqliteEventStore


def _insert_principal(db_path: Path, *, principal_name: str, scopes: list[str]) -> None:
    apply_sqlite_migrations(sqlite_path=db_path)
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


def _insert_acl_rule(
    db_path: Path,
    *,
    sender: str,
    recipient: str,
    action: str,
    allow: bool,
) -> None:
    apply_sqlite_migrations(sqlite_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO acl_rules(rule_id, sender, recipient, action, allow)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), sender, recipient, action, 1 if allow else 0),
        )
        conn.commit()
    finally:
        conn.close()


def _runtime(sqlite_db_path: Path, *, auth_enforce: bool) -> HubRuntime:
    apply_sqlite_migrations(sqlite_path=sqlite_db_path)
    return HubRuntime(
        event_store=SqliteEventStore(sqlite_path=sqlite_db_path),
        auth_enforce=auth_enforce,
    )


def _msg_body(*, sender: str, recipient: str) -> dict[str, str]:
    return {
        "id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": "phase10",
    }


def _hello(name: str, *, role: str = "agent") -> str:
    return json.dumps({"type": "HELLO", "role": role, "name": name})


def _msg_frame(*, sender: str, recipient: str) -> str:
    return json.dumps({"type": "MSG", **_msg_body(sender=sender, recipient=recipient)})


def test_http_report_only_keeps_routing_with_identity_mismatch_and_no_acl(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    runtime = _runtime(sqlite_db_path, auth_enforce=False)
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
            headers={"X-ACP-Principal": "principal_other"},
        )

    assert response.status_code == 200
    assert len(receiver.sent) == 1

    authz = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ"]
    identity = [event for event in authz if event.get("reason_code") == "IDENTITY_MISMATCH"]
    acl = [event for event in authz if event.get("reason_code") == "ACL_NO_RULE"]
    assert identity and identity[-1]["decision"] == "would_deny"
    assert acl and acl[-1]["decision"] == "would_deny"


def test_http_enforce_requires_explicit_principal_header(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["field"] == "from"
    assert body["details"]["reason_code"] == "PRINCIPAL_MISSING"
    assert len(receiver.sent) == 0


def test_http_enforce_denies_identity_mismatch(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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
            headers={"X-ACP-Principal": "principal_other"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["field"] == "from"
    assert body["details"]["reason_code"] == "IDENTITY_MISMATCH"
    assert len(receiver.sent) == 0


def test_http_enforce_denies_when_no_acl_rule(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["send"])
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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
            headers={"X-ACP-Principal": "agent_sender"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["field"] == "to"
    assert body["details"]["reason_code"] == "ACL_NO_RULE"
    assert len(receiver.sent) == 0


def test_http_enforce_allows_when_acl_rule_grants_route(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["send"])
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=True,
    )
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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
            headers={"X-ACP-Principal": "agent_sender"},
        )

    assert response.status_code == 200
    assert len(receiver.sent) == 1
    authz = [event for event in runtime.trace_sink if event.get("event") == "AUTHZ"]
    acl = [event for event in authz if event.get("reason_code") == "ACL_ALLOW"]
    assert acl and acl[-1]["decision"] == "allow"


def test_http_enforce_denies_scope_missing_even_when_acl_allows(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["connect"])
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=True,
    )
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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
            headers={"X-ACP-Principal": "agent_sender"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["field"] == "principal"
    assert body["details"]["reason_code"] == "SCOPE_MISSING"
    assert len(receiver.sent) == 0


def test_http_replay_enforce_denies_when_scope_missing(
    sqlite_db_path: Path,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="observer_live", scopes=["observe"])
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
    app = create_app(runtime=runtime)

    with TestClient(app) as client:
        response = client.get(
            "/replay/events",
            headers={"X-ACP-Principal": "observer_live"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["field"] == "principal"
    assert body["details"]["reason_code"] == "SCOPE_MISSING"


def test_http_enforce_applies_acl_precedence_deny_over_allow(
    sqlite_db_path: Path,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["send"])
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=True,
    )
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=False,
    )
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
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
            headers={"X-ACP-Principal": "agent_sender"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "AUTH_FORBIDDEN"
    assert body["details"]["reason_code"] == "ACL_DENY"
    assert len(receiver.sent) == 0


def test_ws_enforce_denies_acl_missing_with_runtime_error(
    sqlite_db_path: Path,
    run_ingress,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["connect", "send"])
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    sender = websocket_factory(
        [
            _hello("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    assert len(receiver.sent) == 0
    assert sender.sent
    assert sender.sent[-1]["code"] == "AUTH_FORBIDDEN"
    assert sender.sent[-1]["field"] == "to"
    errors = [event for event in runtime.trace_sink if event.get("event") == "ERROR"]
    assert errors and errors[-1]["reason_code"] == "ACL_NO_RULE"


def test_ws_enforce_allows_acl_granted_route(
    sqlite_db_path: Path,
    run_ingress,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["connect", "send"])
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=True,
    )
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    sender = websocket_factory(
        [
            _hello("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    assert len(receiver.sent) == 1
    assert sender.sent == []


def test_ws_enforce_denies_send_scope_missing_even_with_acl_allow(
    sqlite_db_path: Path,
    run_ingress,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["connect"])
    _insert_acl_rule(
        sqlite_db_path,
        sender="agent_sender",
        recipient="agent_receiver",
        action="TASK",
        allow=True,
    )
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
    receiver = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver,
        name="agent_receiver",
    )

    sender = websocket_factory(
        [
            _hello("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    assert len(receiver.sent) == 0
    assert sender.sent
    assert sender.sent[-1]["code"] == "AUTH_FORBIDDEN"
    assert sender.sent[-1]["field"] == "principal"
    errors = [event for event in runtime.trace_sink if event.get("event") == "ERROR"]
    assert errors and errors[-1]["reason_code"] == "SCOPE_MISSING"


def test_ws_enforce_denies_connect_scope_missing_on_hello(
    sqlite_db_path: Path,
    run_ingress,
    websocket_factory,
) -> None:
    _insert_principal(sqlite_db_path, principal_name="agent_sender", scopes=["send"])
    runtime = _runtime(sqlite_db_path, auth_enforce=True)
    sender = websocket_factory([_hello("agent_sender", role="agent")])

    run_ingress(
        sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=runtime.trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
        event_store=runtime.event_store,
    )

    assert sender.closed is True
    assert sender.close_args == {"code": 1008, "reason": "scope-denied"}
    assert sender.sent
    assert sender.sent[-1]["code"] == "AUTH_FORBIDDEN"
    assert sender.sent[-1]["field"] == "name"
    errors = [event for event in runtime.trace_sink if event.get("event") == "ERROR"]
    assert errors and errors[-1]["reason_code"] == "SCOPE_MISSING"
    assert runtime.registry.snapshot_agents() == []
