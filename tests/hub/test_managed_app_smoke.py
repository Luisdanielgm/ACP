from __future__ import annotations

import hashlib
import importlib
import sqlite3
import sys
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from acp.hub.bundle_archive import build_bundle_archive
from acp_managed.auth.sqlite_store import SqliteManagedPrincipalStore


def _load_managed_app():
    sys.modules.pop("acp_managed.app", None)
    return importlib.import_module("acp_managed.app")


def _bootstrap_env(monkeypatch, tmp_path) -> str:
    password = "admin-pass"
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "agent-secret")
    monkeypatch.setenv("ACP_DEPLOYMENT_MODE", "operator")
    monkeypatch.setenv("ACP_PRIVATE_OPERATOR_ENABLED", "true")
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))
    monkeypatch.setenv(
        "ACP_MANAGED_WHITELIST",
        f"admin@example.com={password_hash}:instance_admin,active",
    )
    return password


def _create_managed_app_with_spa(monkeypatch, module, tmp_path):
    dist_dir = tmp_path / "frontend" / "packages" / "managed-app" / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        (
            "<!doctype html><html><body><div id='app'></div>"
            "<script type='module' src='/managed/assets/app.js'></script></body></html>"
        ),
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('managed test shell');", encoding="utf-8")
    monkeypatch.setattr("acp_managed.ui.spa._MANAGED_STATIC_DIR_CANDIDATES", (tmp_path / "static" / "managed", dist_dir))
    return module.create_managed_app()


def _accept_workspace_admin_invitation(client: TestClient, invitation_url: str, *, password: str) -> dict[str, object]:
    path = urlparse(invitation_url).path
    response = client.post(
        f"{path}/accept",
        json={"password": password},
    )
    assert response.status_code == 200
    return response.json()


def test_managed_overlay_mounts_private_surface(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    client = TestClient(_create_managed_app_with_spa(monkeypatch, module, tmp_path))

    home = client.get("/")
    assert home.status_code == 200
    assert "/managed/assets/app.js" in home.text

    legacy_dashboard = client.get("/dashboard", follow_redirects=False)
    assert legacy_dashboard.status_code == 307
    assert legacy_dashboard.headers["location"] == "/managed/login"

    runtime = client.get("/runtime")
    assert runtime.status_code == 200
    payload = runtime.json()
    assert payload["runtime"]["public_web_enabled"] is False
    assert payload["runtime"]["legacy_dashboard_enabled"] is False
    assert payload["runtime"]["coordination_durable"] is True

    login = client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200


def test_instance_admin_invites_workspace_admin_and_accepts_link(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    login = admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200

    create_workspace = admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    )
    assert create_workspace.status_code == 200

    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200
    invite_payload = invite.json()
    assert invite_payload["status"] == "invited"
    assert invite_payload["invitation"]["email"] == "owner@example.com"
    assert "/managed/invitations/" in invite_payload["invitation_url"]

    workspace_client = TestClient(app)
    invitation_page = workspace_client.get(urlparse(invite_payload["invitation_url"]).path)
    assert invitation_page.status_code == 200
    assert "/managed/assets/app.js" in invitation_page.text

    accepted = _accept_workspace_admin_invitation(
        workspace_client,
        invite_payload["invitation_url"],
        password="owner-pass-123",
    )
    assert accepted["status"] == "accepted"
    assert accepted["workspace"]["slug"] == "team-one"
    assert accepted["principal"]["email"] == "owner@example.com"

    workspace_dashboard = workspace_client.get("/managed/ui/workspaces/team-one")
    assert workspace_dashboard.status_code == 200
    assert "/managed/assets/app.js" in workspace_dashboard.text

    second_invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "second@example.com"},
    )
    assert second_invite.status_code == 409


def test_instance_admin_can_create_workspace_and_self_assign_admin(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    login = admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200

    create_workspace = admin_client.post(
        "/managed/admin/workspaces",
        json={
            "slug": "solo-admin",
            "name": "Solo Admin",
            "status": "active",
            "admin_email": "admin@example.com",
        },
    )
    assert create_workspace.status_code == 200
    payload = create_workspace.json()
    assert payload["admin_assignment"] == "self_assigned"
    assert payload["workspace_admin"]["email"] == "admin@example.com"
    assert payload["invitation"] is None
    assert payload["invitation_url"] is None

    my_workspaces = admin_client.get("/managed/workspaces")
    assert my_workspaces.status_code == 200
    slugs = [item["workspace"]["slug"] for item in my_workspaces.json()["workspaces"]]
    assert "solo-admin" in slugs

    workspace_dashboard = admin_client.get("/managed/workspaces/solo-admin")
    assert workspace_dashboard.status_code == 200
    assert workspace_dashboard.json()["workspace_admin"]["email"] == "admin@example.com"


def test_managed_downloads_surface_exposes_bundle_guide_and_skill(monkeypatch, tmp_path) -> None:
    _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    client = TestClient(_create_managed_app_with_spa(monkeypatch, module, tmp_path))

    downloads = client.get("/downloads")
    assert downloads.status_code == 200
    assert "/managed/assets/app.js" in downloads.text

    manifest = client.get("/downloads/ACP_AGENT.json")
    assert manifest.status_code == 200
    assert manifest.json()["version"]

    bundle = client.get("/downloads/ACP_AGENT.zip")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"].startswith("application/zip")

    guide = client.get("/downloads/ACP_AGENT/AGENT.md")
    assert guide.status_code == 200
    assert "ACP Agent Bootstrap" in guide.text

    skill = client.get("/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md")
    assert skill.status_code == 200
    assert "ACP Session Coordinator" in skill.text


def test_managed_download_docs_fall_back_to_bundle_when_source_is_missing(monkeypatch, tmp_path) -> None:
    _bootstrap_env(monkeypatch, tmp_path)
    source_dir = tmp_path / "ACP_AGENT"
    skill_dir = source_dir / "skills" / "acp-session-coordinator"
    skill_dir.mkdir(parents=True)
    (source_dir / "AGENT.md").write_text("# ACP Agent Bootstrap\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("# ACP Session Coordinator\n", encoding="utf-8")
    bundle_path = build_bundle_archive(
        source_dir=source_dir,
        bundle_path=tmp_path / "downloads" / "ACP_AGENT.zip",
    )

    module = _load_managed_app()
    import acp_managed.routing.downloads as downloads_module

    monkeypatch.setattr(downloads_module, "ACP_AGENT_SOURCE_DIR", tmp_path / "missing-ACP_AGENT")
    monkeypatch.setattr(downloads_module, "ensure_bundle_archive", lambda: bundle_path)
    client = TestClient(_create_managed_app_with_spa(monkeypatch, module, tmp_path))

    guide = client.get("/downloads/ACP_AGENT/AGENT.md")
    assert guide.status_code == 200
    assert "ACP Agent Bootstrap" in guide.text

    skill = client.get("/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md")
    assert skill.status_code == 200
    assert "ACP Session Coordinator" in skill.text


def test_workspace_admin_rotates_single_token_and_agent_uses_it(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )

    rotate_one = workspace_client.post("/managed/workspaces/team-one/token/rotate")
    assert rotate_one.status_code == 200
    token_one = rotate_one.json()["raw_token"]

    rotate_two = workspace_client.post("/managed/workspaces/team-one/token/rotate")
    assert rotate_two.status_code == 200
    token_two = rotate_two.json()["raw_token"]
    assert token_one != token_two

    stale_create = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {token_one}"},
        json={"agent_name": "chief-agent", "title": "Sprint", "project": "ACP"},
    )
    assert stale_create.status_code == 401

    create_session = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {token_two}"},
        json={"agent_name": "chief-agent", "title": "Sprint", "project": "ACP"},
    )
    assert create_session.status_code == 200
    session_payload = create_session.json()
    assert session_payload["status"] == "created"
    assert session_payload["workspace"]["slug"] == "team-one"
    assert session_payload["acp_session"]["join_code"]

    duplicate_create = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {token_two}"},
        json={"agent_name": "chief-agent", "title": "Sprint duplicate", "project": "ACP"},
    )
    assert duplicate_create.status_code == 200
    duplicate_payload = duplicate_create.json()
    assert duplicate_payload["status"] == "created"
    assert duplicate_payload["workspace_session"]["owner_agent_name"].startswith("chief-agent--team-one")
    assert duplicate_payload["workspace_session"]["owner_agent_name"] != "chief-agent"

    revoke = workspace_client.post("/managed/workspaces/team-one/token/revoke")
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    revoked_create = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {token_two}"},
        json={"agent_name": "chief-agent", "title": "Sprint 2", "project": "ACP"},
    )
    assert revoked_create.status_code == 401


def test_workspace_token_creates_session_and_guest_joins_via_join_code(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )
    token_payload = workspace_client.post("/managed/workspaces/team-one/token/rotate").json()
    raw_token = token_payload["raw_token"]
    share_prompt = token_payload["bootstrap"]["share_prompt"]
    assert "managed-start" in share_prompt
    assert "managed-join" in share_prompt
    assert "managed-close" in share_prompt
    assert "replay" in share_prompt
    assert "onboard" in share_prompt
    assert "onboard_worker" in token_payload["bootstrap"]["command_examples"]
    assert "chief start" in share_prompt
    assert "chief_start" in token_payload["bootstrap"]["command_examples"]
    assert "POST /sessions/send" in share_prompt
    assert token_payload["bootstrap"]["managed_routes"]["session_close_template"].endswith("/managed/agent/sessions/{session_id}/close")
    assert token_payload["bootstrap"]["managed_routes"]["session_replay_template"].endswith("/managed/agent/sessions/{session_id}/replay")
    assert "managed_replay" in token_payload["bootstrap"]["command_examples"]
    assert token_payload["bootstrap"]["rest_examples"]["managed_replay"]["method"] == "GET"
    assert token_payload["bootstrap"]["rest_examples"]["send_message"]["headers"] == {
        "X-ACP-Member-Token": "<member-token>"
    }
    assert "SESSION_ID" in share_prompt
    assert "No lo uses como ACP_TOKEN global" in share_prompt

    create_session = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "chief-agent", "title": "Sprint", "project": "ACP"},
    )
    assert create_session.status_code == 200
    created_payload = create_session.json()
    join_code = created_payload["acp_session"]["join_code"]
    session_id = created_payload["workspace_session"]["session_id"]
    assert created_payload["session_id"] == session_id
    assert created_payload["join_code"] == join_code
    assert created_payload["member_token"] == created_payload["acp_session"]["member_token"]

    duplicate_join = admin_client.post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/join",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "chief-agent"},
    )
    assert duplicate_join.status_code == 409
    assert "already attached" in duplicate_join.json()["detail"]

    managed_join = admin_client.post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/join",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "managed-helper"},
    )
    assert managed_join.status_code == 200
    managed_join_payload = managed_join.json()
    assert managed_join_payload["status"] == "joined"
    assert managed_join_payload["session_id"] == session_id
    assert managed_join_payload["member_token"] == managed_join_payload["acp_session"]["member_token"]

    join = admin_client.post(
        "/sessions/join",
        json={"agent_name": "helper-agent", "join_code": join_code},
    )
    assert join.status_code == 200
    join_payload = join.json()
    assert join_payload["status"] == "ok"
    assert join_payload["member_role"] == "collaborator"
    member_token = join_payload["member_token"]

    status = admin_client.post(
        "/sessions/status",
        json={
            "session_id": session_id,
            "agent_name": "helper-agent",
            "member_token": member_token,
            "status": "waiting",
            "status_text": "ready",
        },
    )
    assert status.status_code == 200
    assert status.json()["status"] == "ok"
    assert status.json()["member"]["status"] == "waiting"

    session_detail = workspace_client.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert session_detail.status_code == 200
    detail_payload = session_detail.json()
    assert detail_payload["session_id"] == session_id
    assert detail_payload["acp_session"]["join_code"] == join_code
    member_names = [item["agent_name"] for item in detail_payload["acp_session"]["members"]]
    assert "helper-agent" in member_names


def test_managed_agent_replay_exposes_session_history(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )
    raw_token = workspace_client.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]

    create_session = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "chief-agent", "title": "Replay sprint", "project": "ACP"},
    )
    assert create_session.status_code == 200
    created = create_session.json()
    session_id = created["session_id"]
    chief_token = created["member_token"]
    join_code = created["join_code"]

    joined = admin_client.post(
        "/sessions/join",
        json={"agent_name": "worker-agent", "join_code": join_code},
    )
    assert joined.status_code == 200
    worker_token = joined.json()["member_token"]

    assert admin_client.post(
        "/sessions/send",
        json={
            "session_id": session_id,
            "agent_name": "chief-agent",
            "member_token": chief_token,
            "to": "worker-agent",
            "action": "TASK",
            "payload": "Review replay.",
        },
    ).status_code == 200
    assert admin_client.post(
        "/sessions/send",
        json={
            "session_id": session_id,
            "agent_name": "worker-agent",
            "member_token": worker_token,
            "to": "chief-agent",
            "action": "REPLY",
            "payload": {"task_id": "replay", "outcome": "success"},
        },
    ).status_code == 200

    replay = admin_client.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/replay",
        headers={"Authorization": f"Bearer {raw_token}"},
        params={"actor": "worker-agent", "action": "REPLY", "limit": 5},
    )
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["workspace_session"]["session_id"] == session_id
    assert payload["events"]
    event_payload = payload["events"][0]["payload"]
    assert event_payload["session_id"] == session_id
    assert event_payload["actor"] == "worker-agent"
    assert event_payload["action"] == "REPLY"
    assert "owner_member_token" not in payload["workspace_session"]


def test_owner_member_token_exposed_to_admin_but_never_to_agent_tokens(monkeypatch, tmp_path) -> None:
    # The managed SPA builds the operator dashboard URL from
    # workspace_session.owner_member_token. That field must reach cookie
    # workspace_admins (same trust boundary as the server-side /live redirect)
    # but must NEVER appear in agent-token (Bearer) responses, or any holder of
    # a workspace token could operate another agent's session as its chief.
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )

    create = workspace_client.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief-agent", "title": "Sprint", "project": "ACP"},
    )
    assert create.status_code == 200
    created = create.json()
    owner_token = created["member_token"]
    session_id = created["workspace_session"]["session_id"]
    assert owner_token
    # Cookie create response carries the operator token on the session object.
    assert created["workspace_session"]["owner_member_token"] == owner_token

    # Per-session detail (consumed by SessionLiveView) exposes the operator token.
    detail = workspace_client.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["workspace_session"]["owner_member_token"] == owner_token

    # Workspace detail list (consumed by WorkspaceDetailView cards) exposes it.
    ws_detail = workspace_client.get("/managed/workspaces/team-one")
    assert ws_detail.status_code == 200
    assert any(
        item["session_id"] == session_id and item.get("owner_member_token") == owner_token
        for item in ws_detail.json()["sessions"]
    )

    # Sessions list endpoint exposes it as well.
    sessions_list = workspace_client.get("/managed/workspaces/team-one/sessions")
    assert sessions_list.status_code == 200
    assert any(
        item["session_id"] == session_id and item.get("owner_member_token") == owner_token
        for item in sessions_list.json()["sessions"]
    )

    # SECURITY: agent-token (Bearer) responses must NOT leak the owner member token.
    raw_token = workspace_client.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    agent_detail = admin_client.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert agent_detail.status_code == 200
    assert "owner_member_token" not in agent_detail.json()["workspace_session"]

    agent_list = admin_client.get(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert agent_list.status_code == 200
    for item in agent_list.json()["sessions"]:
        assert "owner_member_token" not in item


def test_managed_agent_token_can_close_and_cleanup_workspace_sessions(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )
    raw_token = workspace_client.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]

    create_session = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "chief-agent", "title": "Cleanup live", "project": "ACP"},
    )
    assert create_session.status_code == 200
    session_id = create_session.json()["workspace_session"]["session_id"]

    close_session = admin_client.post(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/close",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"detail": "Work complete"},
    )
    assert close_session.status_code == 200
    close_payload = close_session.json()
    assert close_payload["status"] == "closed"
    assert close_payload["session_closed"] is True
    assert close_payload["workspace_session_deleted"] is True
    assert close_payload["close_error"] is None

    list_after_close = admin_client.get(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert list_after_close.status_code == 200
    assert list_after_close.json()["sessions"] == []

    create_stale_session = admin_client.post(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"agent_name": "chief-agent", "title": "Cleanup stale", "project": "ACP"},
    )
    assert create_stale_session.status_code == 200
    stale_session_id = create_stale_session.json()["workspace_session"]["session_id"]

    dashboard_close = workspace_client.post(
        f"/sessions/{stale_session_id}/admin/close",
        json={"detail": "Dashboard closed first"},
    )
    assert dashboard_close.status_code == 200

    cleanup_stale = admin_client.post(
        f"/managed/agent/workspaces/team-one/sessions/{stale_session_id}/close",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"detail": "Cleanup stale managed record"},
    )
    assert cleanup_stale.status_code == 200
    cleanup_payload = cleanup_stale.json()
    assert cleanup_payload["status"] == "already-gone"
    assert cleanup_payload["session_closed"] is False
    assert cleanup_payload["core_session_already_gone"] is True
    assert cleanup_payload["workspace_session_deleted"] is True
    assert cleanup_payload["close_error"] is None

    final_list = admin_client.get(
        "/managed/agent/workspaces/team-one/sessions",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert final_list.status_code == 200
    assert final_list.json()["sessions"] == []


def test_workspace_admin_can_create_session_from_workspace_panel(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client,
        invite.json()["invitation_url"],
        password="owner-pass-123",
    )

    create_session_page = workspace_client.post(
        "/managed/ui/workspaces/team-one/sessions/create",
        data={"agent_name": "chief-agent", "title": "Sprint", "project": "ACP"},
        follow_redirects=False,
    )
    assert create_session_page.status_code == 303
    assert create_session_page.headers["location"].startswith("/managed/ui/workspaces/team-one/sessions/")

    sessions_payload = workspace_client.get("/managed/workspaces/team-one/sessions")
    assert sessions_payload.status_code == 200
    session_id = sessions_payload.json()["sessions"][0]["session_id"]

    admin_session_detail = workspace_client.get(
        f"/sessions/{session_id}/detail",
        params={"agent_name": "chief-agent"},
    )
    assert admin_session_detail.status_code == 200
    assert admin_session_detail.json()["session"]["session_id"] == session_id

    sessions_page = workspace_client.get("/managed/ui/workspaces/team-one/sessions")
    assert sessions_page.status_code == 200
    assert "/managed/assets/app.js" in sessions_page.text

    session_detail_page = workspace_client.get(f"/managed/ui/workspaces/team-one/sessions/{session_id}")
    assert session_detail_page.status_code == 200
    assert "/managed/assets/app.js" in session_detail_page.text

    live_redirect = workspace_client.get(
        f"/managed/ui/workspaces/team-one/sessions/{session_id}/live",
        follow_redirects=False,
    )
    assert live_redirect.status_code == 307
    location = live_redirect.headers["location"]
    assert "/managed/dashboard/session?session_id=" in location
    assert "agent_name=chief-agent" in location
    parsed_location = urlparse(location)
    assert "member_token=" not in parsed_location.query
    assert "member_token=" in parsed_location.fragment


def test_workspace_admin_creates_team_preset_via_json(monkeypatch, tmp_path) -> None:
    # X-LEGACY-01 (fixed): the SPA posts JSON {preset_id} to this endpoint and
    # expects a JSON response. It must accept a JSON body (not form) and must not
    # redirect.
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    assert admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    ).status_code == 200
    assert admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    ).status_code == 200
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    assert invite.status_code == 200

    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client, invite.json()["invitation_url"], password="owner-pass-123"
    )

    response = workspace_client.post(
        "/managed/admin/workspaces/team-one/presets/create",
        json={"preset_id": "chief-reviewer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["preset_id"] == "chief-reviewer"


def test_workspace_admin_create_preset_rejects_unknown_preset(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    )
    invite = admin_client.post(
        "/managed/admin/workspaces/team-one/invite-admin",
        json={"email": "owner@example.com"},
    )
    workspace_client = TestClient(app)
    _accept_workspace_admin_invitation(
        workspace_client, invite.json()["invitation_url"], password="owner-pass-123"
    )

    response = workspace_client.post(
        "/managed/admin/workspaces/team-one/presets/create",
        json={"preset_id": "does-not-exist"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "invalid_secret",
    ["", "replace-me", "dev-insecure-secret", "change_me"],
)
def test_managed_overlay_rejects_placeholder_session_secret(monkeypatch, tmp_path, invalid_secret: str) -> None:
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", invalid_secret)
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_WHITELIST", "")

    with pytest.raises(ValueError, match="ACP_MANAGED_SESSION_SECRET"):
        _load_managed_app()


def test_managed_overlay_rejects_placeholder_agent_token_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "replace-me")
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_WHITELIST", "")

    with pytest.raises(ValueError, match="ACP_MANAGED_AGENT_TOKEN_SECRET"):
        _load_managed_app()


def test_managed_store_adds_owner_member_token_column_to_existing_workspace_sessions_table(tmp_path) -> None:
    db_path = tmp_path / "managed-auth.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE managed_principals (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE managed_workspaces (
                workspace_id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE managed_workspace_memberships (
                workspace_id TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (workspace_id, email)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE managed_workspace_sessions (
                session_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                created_by_email TEXT NOT NULL,
                owner_agent_name TEXT NOT NULL,
                title TEXT NULL,
                project TEXT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    SqliteManagedPrincipalStore(sqlite_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(managed_workspace_sessions)").fetchall()
        }
    finally:
        conn.close()

    assert "owner_member_token" in columns


def test_invitation_accept_for_existing_account_requires_password(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)
    admin_client = TestClient(app)

    login = admin_client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200

    create_workspace = admin_client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-existing", "name": "Team Existing", "status": "active"},
    )
    assert create_workspace.status_code == 200

    # Invite an email that ALREADY has an account (the instance_admin itself).
    invite = admin_client.post(
        "/managed/admin/workspaces/team-existing/invite-admin",
        json={"email": "admin@example.com"},
    )
    assert invite.status_code == 200
    invitation_url = invite.json()["invitation_url"]

    # A holder of the invitation link must NOT receive a session for an existing
    # account without the correct password.
    attacker = TestClient(app)
    resp = attacker.post(
        f"{urlparse(invitation_url).path}/accept",
        json={"password": "totally-wrong-password"},
    )
    assert resp.status_code == 401
    assert "acp_managed_session" not in resp.headers.get("set-cookie", "")
