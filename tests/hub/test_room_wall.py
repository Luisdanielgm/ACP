"""Persistent room wall â€” M3 slice 2.

The room wall is product context, not replay/audit history. It is persisted as
separate posts attached to a managed workspace session. Owners and agents can
post; only the owner/admin surface can pin or delete posts in v1.
"""

from __future__ import annotations

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


def test_room_wall_is_separate_persistent_context_for_owner_and_agents(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)

    owner_post = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/wall",
        json={"body": "Pinned: stay focused on the room wall slice.", "pinned": True},
    )
    assert owner_post.status_code == 200, owner_post.text
    owner_item = owner_post.json()["post"]
    assert owner_item["author_type"] == "owner"
    assert owner_item["author_name"] == "admin@example.com"
    assert owner_item["pinned"] is True

    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    agent = TestClient(app)
    agent_post = agent.post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/wall",
        headers={"Authorization": f"Bearer {token}"},
        json={"agent_name": "worker-1", "body": "Worker is ready for the next task."},
    )
    assert agent_post.status_code == 200, agent_post.text
    agent_item = agent_post.json()["post"]
    assert agent_item["author_type"] == "agent"
    assert agent_item["author_name"] == "worker-1"
    assert agent_item["pinned"] is False

    owner_wall = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/wall")
    assert owner_wall.status_code == 200, owner_wall.text
    owner_payload = owner_wall.json()
    assert [item["post_id"] for item in owner_payload["posts"]] == [
        owner_item["post_id"],
        agent_item["post_id"],
    ]
    assert owner_payload["posts"][0]["body"].startswith("Pinned:")

    agent_wall = agent.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/wall",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_wall.status_code == 200, agent_wall.text
    agent_payload = agent_wall.json()
    assert [item["body"] for item in agent_payload["posts"]] == [
        "Pinned: stay focused on the room wall slice.",
        "Worker is ready for the next task.",
    ]
    assert "owner_member_token" not in agent_payload["workspace_session"]

    agent_delete = agent.delete(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/wall/{owner_item['post_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_delete.status_code == 404


def test_room_wall_owner_can_pin_and_delete_posts(monkeypatch, tmp_path) -> None:
    _, owner, session_id = _owner_with_session(monkeypatch, tmp_path)

    created = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/wall",
        json={"body": "Decision: wall is separate from replay.", "pinned": False},
    )
    assert created.status_code == 200, created.text
    post_id = created.json()["post"]["post_id"]

    pinned = owner.patch(
        f"/managed/workspaces/team-one/sessions/{session_id}/wall/{post_id}",
        json={"pinned": True},
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["post"]["pinned"] is True

    deleted = owner.delete(f"/managed/workspaces/team-one/sessions/{session_id}/wall/{post_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"

    wall = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/wall")
    assert wall.status_code == 200, wall.text
    assert wall.json()["posts"] == []
