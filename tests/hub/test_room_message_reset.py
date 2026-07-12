"""Administrative room-message reset preserves durable room context."""

from __future__ import annotations

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
    _login_workspace_admin,
)
from test_web_operator import _join_worker


def _owner_with_session(monkeypatch, tmp_path) -> tuple[object, TestClient, str]:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)
    created = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief", "title": "Daily coordination", "project": "ACP"},
    )
    assert created.status_code == 200, created.text
    return app, owner, created.json()["workspace_session"]["session_id"]


def test_workspace_admin_resets_messages_without_resetting_room_context(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    worker = _join_worker(app, owner, session_id=session_id)
    wall = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/wall",
        json={"body": "Permanent room instruction", "pinned": True},
    )
    assert wall.status_code == 200, wall.text

    for payload in ("First pending task", "Second pending task"):
        sent = owner.post(
            f"/managed/workspaces/team-one/sessions/{session_id}/operator/send",
            json={"to": "worker-1", "action": "TASK", "payload": payload},
        )
        assert sent.status_code == 200, sent.text

    before = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}").json()["acp_session"]
    before_member = next(item for item in before["members"] if item["agent_name"] == "worker-1")
    assert before_member["pending_count"] == 2
    assert any(item["event"] == "MESSAGE_SENT" for item in before["history"])

    reset = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/messages/reset",
        json={"reason": "Start a clean coordination cycle"},
    )

    assert reset.status_code == 200, reset.text
    payload = reset.json()
    assert payload["status"] == "messages_reset"
    assert payload["session_id"] == session_id
    assert payload["cleared_pending_messages"] == 2
    assert payload["preserved"] == ["session", "members", "wall", "files", "operator"]

    after = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}").json()["acp_session"]
    assert not any(item["event"].startswith("MESSAGE_") for item in after["history"])
    assert any(item["event"] == "MESSAGES_RESET" for item in after["history"])
    member = next(item for item in after["members"] if item["agent_name"] == "worker-1")
    assert member["pending_count"] == 0
    assert member["current_task"] is None
    assert member["status"] == "waiting"

    wait = TestClient(app).post(
        "/sessions/wait",
        json={
            "session_id": session_id,
            "agent_name": worker["agent_name"],
            "member_token": worker["member_token"],
            "timeout_seconds": 0.05,
        },
    )
    assert wait.status_code == 200, wait.text
    notice = wait.json()["message"]
    assert notice["system_event"] == "MESSAGES_RESET"
    assert notice["session_closed"] is False
    assert notice["to"] == "worker-1"
    second_wait = TestClient(app).post(
        "/sessions/wait",
        json={
            "session_id": session_id,
            "agent_name": worker["agent_name"],
            "member_token": worker["member_token"],
            "timeout_seconds": 0.05,
        },
    )
    assert second_wait.json() == {"status": "timeout"}
    wall_after = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/wall").json()
    assert [item["body"] for item in wall_after["posts"]] == ["Permanent room instruction"]


def test_room_member_cannot_invoke_administrative_message_reset(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]

    denied = TestClient(app).post(
        f"/managed/workspaces/team-one/sessions/{session_id}/messages/reset",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "member request"},
    )

    assert denied.status_code in {401, 403}


def test_workspace_integration_token_can_reset_but_agent_bound_token_cannot(monkeypatch, tmp_path) -> None:
    _, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    workspace_token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    allowed = TestClient(owner.app).post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/messages/reset",
        headers={"Authorization": f"Bearer {workspace_token}"},
        json={"reason": "Reset requested by host administration"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "messages_reset"

    issued = owner.post(
        "/managed/workspaces/team-one/agent-tokens",
        json={"label": "Support Manager", "agent_name": "support-manager"},
    )
    assert issued.status_code == 200, issued.text
    agent_token = issued.json()["raw_token"]
    denied = TestClient(owner.app).post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/messages/reset",
        headers={"Authorization": f"Bearer {agent_token}"},
        json={"reason": "Agent request"},
    )
    assert denied.status_code == 403
