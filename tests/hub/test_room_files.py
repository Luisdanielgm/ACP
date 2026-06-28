"""Managed room files — M4 storage slice 1.

Room files are durable per-session storage, separate from wall posts and replay.
The owner can upload/delete; agents can read/download through their workspace
agent token without receiving owner credentials.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _accept_workspace_admin_invitation,
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
)


def _owner_with_session(monkeypatch, tmp_path) -> tuple[object, TestClient, str]:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)

    admin = TestClient(app)
    assert admin.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    owner = TestClient(app)
    _accept_workspace_admin_invitation(owner, invite.json()["invitation_url"], password="owner-pass-123")

    created = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief", "title": "Sprint", "project": "ACP"},
    )
    assert created.status_code == 200, created.text
    return app, owner, created.json()["workspace_session"]["session_id"]


def _workspace_agent_token(owner: TestClient) -> str:
    rotated = owner.post("/managed/workspaces/team-one/token/rotate")
    assert rotated.status_code == 200, rotated.text
    return rotated.json()["raw_token"]


def test_room_files_owner_uploads_and_agents_can_read_without_owner_token(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)

    uploaded = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/files",
        files={"file": ("decision.md", b"# Decision\nUse room files for durable artifacts.\n", "text/markdown")},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_item = uploaded.json()["file"]
    assert uploaded.json()["status"] == "created"
    assert file_item["filename"] == "decision.md"
    assert file_item["content_type"] == "text/markdown"
    assert file_item["size_bytes"] == len(b"# Decision\nUse room files for durable artifacts.\n")
    assert file_item["uploaded_by_type"] == "owner"
    assert file_item["uploaded_by_name"] == "owner@example.com"
    assert "content" not in file_item

    owner_list = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/files")
    assert owner_list.status_code == 200, owner_list.text
    assert owner_list.json()["count"] == 1
    assert owner_list.json()["files"][0]["file_id"] == file_item["file_id"]

    owner_download = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/files/{file_item['file_id']}")
    assert owner_download.status_code == 200, owner_download.text
    assert owner_download.content == b"# Decision\nUse room files for durable artifacts.\n"
    assert owner_download.headers["content-type"].startswith("text/markdown")

    token = _workspace_agent_token(owner)
    agent = TestClient(app)
    agent_list = agent.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/files",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_list.status_code == 200, agent_list.text
    agent_payload = agent_list.json()
    assert agent_payload["files"][0]["filename"] == "decision.md"
    assert "owner_member_token" not in agent_payload["workspace_session"]

    agent_download = agent.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/files/{file_item['file_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_download.status_code == 200, agent_download.text
    assert agent_download.content == b"# Decision\nUse room files for durable artifacts.\n"

    agent_delete = agent.delete(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/files/{file_item['file_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_delete.status_code == 405


def test_room_files_owner_can_delete_and_large_files_are_rejected(monkeypatch, tmp_path) -> None:
    _, owner, session_id = _owner_with_session(monkeypatch, tmp_path)

    too_large = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/files",
        files={"file": ("huge.txt", b"x" * (257 * 1024), "text/plain")},
    )
    assert too_large.status_code == 413, too_large.text

    uploaded = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/files",
        files={"file": ("notes.txt", b"short notes", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file"]["file_id"]

    deleted = owner.delete(f"/managed/workspaces/team-one/sessions/{session_id}/files/{file_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"

    listing = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}/files")
    assert listing.status_code == 200, listing.text
    assert listing.json()["files"] == []
