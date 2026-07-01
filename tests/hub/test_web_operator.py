"""Managed Web operator — M3 slice 3.

A browser workspace admin can operate inside a managed room as a server-side
pseudo-member. The browser must never receive that pseudo-member token; the
backend owns it and sends coordination messages on the admin's behalf.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _login_workspace_admin,
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
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


def test_web_operator_sends_as_server_side_pseudo_member_without_token_leak(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    worker = _join_worker(app, owner, session_id=session_id)

    sent = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
        json={"to": "worker-1", "action": "TASK", "payload": "Review the room wall slice."},
    )
    assert sent.status_code == 200, sent.text
    sent_payload = sent.json()
    operator_name = sent_payload["operator"]["agent_name"]
    assert sent_payload["status"] == "sent"
    assert sent_payload["operator"]["created"] is True
    assert operator_name.startswith("web-operator-")
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
    assert message["from"] == operator_name
    assert message["to"] == "worker-1"
    assert message["action"] == "TASK"
    assert message["payload"] == "Review the room wall slice."


def test_web_operator_reuses_existing_pseudo_member_for_same_admin(monkeypatch, tmp_path) -> None:
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
    assert first_operator["agent_name"] == second_operator["agent_name"]
    assert first_operator["created"] is True
    assert second_operator["created"] is False
    assert "member_token" not in json.dumps(second.json())

    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert detail.status_code == 200, detail.text
    members = detail.json()["acp_session"]["members"]
    operator_members = [item for item in members if item["agent_name"] == first_operator["agent_name"]]
    assert len(operator_members) == 1
