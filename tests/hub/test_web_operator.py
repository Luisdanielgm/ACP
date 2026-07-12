"""Managed room operator messages use the room's technical chief identity."""

from __future__ import annotations

import json
from dataclasses import replace

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
    _login_workspace_admin,
)


def _owner_with_session(monkeypatch, tmp_path) -> tuple[object, TestClient, str]:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)

    admin = TestClient(app)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)

    created = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief", "title": "Sprint", "project": "ACP"},
    )
    assert created.status_code == 200, created.text
    return app, owner, created.json()["workspace_session"]["session_id"]


def _join_worker(app: object, owner: TestClient, *, session_id: str, agent_name: str = "worker-1") -> dict[str, object]:
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    agent = TestClient(app)
    joined = agent.post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/join",
        headers={"Authorization": f"Bearer {token}"},
        json={"agent_name": agent_name, "capabilities": ["tasks"]},
    )
    assert joined.status_code == 200, joined.text
    payload = joined.json()
    return {
        "agent_name": agent_name,
        "member_token": payload["member_token"],
    }


def test_web_operator_sends_as_room_chief_without_token_leak(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    worker = _join_worker(app, owner, session_id=session_id)

    sent = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
        json={"to": "worker-1", "action": "TASK", "payload": "Review the room wall slice."},
    )
    assert sent.status_code == 200, sent.text
    sent_payload = sent.json()
    assert sent_payload["status"] == "sent"
    assert sent_payload["operator"] == {
        "operator_id": f"session-owner:{session_id}",
        "agent_name": "chief",
        "created": False,
        "identity_source": "session_owner",
    }
    assert "member_token" not in json.dumps(sent_payload)

    delivered = TestClient(app).post(
        "/sessions/wait",
        json={
            "session_id": session_id,
            "agent_name": worker["agent_name"],
            "member_token": worker["member_token"],
            "timeout_seconds": 0.1,
        },
    )
    assert delivered.status_code == 200, delivered.text
    message = delivered.json()["message"]
    assert message["from"] == "chief"
    assert message["to"] == "worker-1"
    assert message["action"] == "TASK"
    assert message["payload"] == "Review the room wall slice."

    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert detail.status_code == 200, detail.text
    members = detail.json()["acp_session"]["members"]
    assert all(not item["agent_name"].startswith("web-operator-") for item in members)

    audit_events = app.state.managed_principal_store.list_audit_events(
        action="managed.room_operator_message_sent",
    )
    assert len(audit_events) == 1
    audit = audit_events[0]
    assert audit.actor_email == "admin@example.com"
    assert audit.target_type == "workspace_session"
    assert audit.target_id == session_id
    metadata = json.loads(audit.metadata_json or "{}")
    assert metadata == {
        "action": "TASK",
        "identity_source": "session_owner",
        "message_id": sent_payload["message"]["id"],
        "operator_agent_name": "chief",
        "to": "worker-1",
        "workspace_id": sent_payload["workspace"]["workspace_id"],
        "workspace_slug": "team-one",
    }
    assert "Review the room wall slice." not in (audit.metadata_json or "")
    assert "token" not in (audit.metadata_json or "").lower()


def test_web_operator_reuses_room_chief_without_creating_members(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    _join_worker(app, owner, session_id=session_id)

    first = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
        json={"to": "worker-1", "action": "INFO", "payload": "First note."},
    )
    assert first.status_code == 200, first.text

    second = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
        json={"to": "worker-1", "action": "INFO", "payload": "Second note."},
    )
    assert second.status_code == 200, second.text

    first_operator = first.json()["operator"]
    second_operator = second.json()["operator"]
    assert first_operator["agent_name"] == second_operator["agent_name"] == "chief"
    assert first_operator["created"] is False
    assert second_operator["created"] is False
    assert first_operator["identity_source"] == second_operator["identity_source"] == "session_owner"
    assert "member_token" not in json.dumps(second.json())

    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert detail.status_code == 200, detail.text
    members = detail.json()["acp_session"]["members"]
    assert [item["agent_name"] for item in members].count("chief") == 1
    assert all(not item["agent_name"].startswith("web-operator-") for item in members)


def test_web_operator_receives_queued_message_for_room_chief(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    worker = _join_worker(app, owner, session_id=session_id)

    sent = TestClient(app).post(
        "/sessions/send",
        json={
            "session_id": session_id,
            "agent_name": worker["agent_name"],
            "member_token": worker["member_token"],
            "to": "chief",
            "action": "REPLY",
            "payload": "Full reply body that the dashboard chief must be able to read.",
        },
    )
    assert sent.status_code == 200, sent.text

    received = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/receive",
        json={},
    )
    assert received.status_code == 200, received.text
    payload = received.json()
    assert payload["status"] == "delivered"
    message = payload["message"]
    assert message["from"] == "worker-1"
    assert message["to"] == "chief"
    assert message["action"] == "REPLY"
    assert message["payload"] == "Full reply body that the dashboard chief must be able to read."
    assert payload["operator"]["agent_name"] == "chief"
    assert payload["operator"]["identity_source"] == "session_owner"
    assert "member_token" not in json.dumps(payload)

    audit_events = app.state.managed_principal_store.list_audit_events(
        action="managed.room_operator_message_received",
    )
    assert len(audit_events) == 1
    metadata = json.loads(audit_events[0].metadata_json or "{}")
    assert metadata["message_id"] == message["id"]
    assert metadata["operator_agent_name"] == "chief"
    assert "Full reply body" not in (audit_events[0].metadata_json or "")


def test_web_operator_receive_reports_empty_inbox(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    _join_worker(app, owner, session_id=session_id)

    received = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/receive",
        json={"timeout_seconds": 0},
    )
    assert received.status_code == 200, received.text
    payload = received.json()
    assert payload["status"] == "empty"
    assert payload["message"] is None


def test_web_operator_receive_conflicts_without_owner_identity(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    store = app.state.managed_principal_store
    original_get_workspace_session = store.get_workspace_session

    def legacy_workspace_session(*, session_id: str):
        record = original_get_workspace_session(session_id=session_id)
        return None if record is None else replace(record, owner_member_token=None)

    monkeypatch.setattr(store, "get_workspace_session", legacy_workspace_session)

    received = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/receive",
        json={},
    )
    assert received.status_code == 409, received.text


def test_web_operator_falls_back_for_legacy_room_without_owner_token(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    _join_worker(app, owner, session_id=session_id)
    store = app.state.managed_principal_store
    original_get_workspace_session = store.get_workspace_session

    def legacy_workspace_session(*, session_id: str):
        record = original_get_workspace_session(session_id=session_id)
        return None if record is None else replace(record, owner_member_token=None)

    monkeypatch.setattr(store, "get_workspace_session", legacy_workspace_session)

    sent = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
        json={"to": "worker-1", "action": "INFO", "payload": "Legacy room note."},
    )
    assert sent.status_code == 200, sent.text
    operator = sent.json()["operator"]
    assert operator["agent_name"].startswith("web-operator-")
    assert operator["created"] is True
    assert operator["identity_source"] == "legacy_web_operator"
    assert "member_token" not in json.dumps(sent.json())
