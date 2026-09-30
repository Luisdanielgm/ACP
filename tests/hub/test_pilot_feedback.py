"""Pilot-report behaviors: join-code rejection reasons, operator approvals,
human-mediator owner, permanent rooms (D13, B8, C9, C12)."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
    _login_workspace_admin,
)
from test_web_operator import _join_worker, _owner_with_session


# ── D13: join-code rejection reasons ─────────────────────────────────────────


def _create_core_session(client: Any, agent_name: str = "chief") -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name})
    assert response.status_code == 201
    return response.json()


def _join(client: Any, code: str, agent_name: str = "worker") -> Any:
    return client.post("/sessions/join", json={"agent_name": agent_name, "join_code": code})


def test_join_code_wrong_length_reports_expected_and_actual(api_client: Any) -> None:
    response = _join(api_client, "ABCDEF0123")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "INVALID_FIELD"
    assert body["field"] == "join_code"
    assert body["reason"] == "invalid_format"
    # Legacy substring kept for clients that match on it.
    assert "join code is invalid" in body["message"]
    assert "expected 8 characters" in body["message"]
    assert "got 10" in body["message"]
    assert "ABCDEF0123" not in body["message"]


def test_join_code_stray_quotes_are_invalid_format(api_client: Any) -> None:
    response = _join(api_client, "'ABCD12'")
    assert response.status_code == 409
    assert response.json()["reason"] == "invalid_format"


def test_join_code_unknown_is_generic(api_client: Any) -> None:
    response = _join(api_client, "DEADBEEF")
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "unknown"
    assert "join code is invalid" in body["message"]
    assert "unknown code" in body["message"]


def test_join_code_of_closed_session_reports_session_closed(api_client: Any) -> None:
    created = _create_core_session(api_client)
    closed = api_client.post(f"/sessions/{created['session_id']}/admin/close", json={})
    assert closed.status_code == 200
    response = _join(api_client, created["join_code"])
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "session_closed"
    assert "join code is invalid" in body["message"]
    assert "closed" in body["message"]


def test_join_code_of_stale_cleaned_session_reports_expired(api_client: Any, hub_runtime: Any) -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    created = _create_core_session(api_client)
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    store = hub_runtime.coordination._store
    session = store.get_session(created["session_id"])
    for member in session.members.values():
        member.last_seen_at = stale_at
        store.update_member(created["session_id"], member)
    hub_runtime.coordination._last_cleanup_at = None
    removed = asyncio.run(hub_runtime.coordination.cleanup_stale_sessions())
    assert created["session_id"] in removed
    response = _join(api_client, created["join_code"])
    assert response.status_code == 409
    assert response.json()["reason"] == "expired"


def test_join_with_name_of_session_owner_says_so(api_client: Any) -> None:
    created = _create_core_session(api_client, "boss")
    response = _join(api_client, created["join_code"], agent_name="boss")
    assert response.status_code == 409
    message = response.json()["message"]
    assert "taken by the session owner" in message
    # Legacy phrase preserved.
    assert "already attached to another session" in message


# ── B8: operator approvals ───────────────────────────────────────────────────


def test_operator_approval_is_stored_broadcast_and_verifiable(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    worker = _join_worker(app, owner, session_id=session_id)
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]

    created = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator-approvals",
        json={"text": "Approved: run the migration on staging."},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    approval = body["approval"]
    assert approval["text"] == "Approved: run the migration on staging."
    assert approval["session_id"] == session_id
    assert approval["approval_id"]
    assert approval["created_at"]
    assert "member_token" not in json.dumps(body)

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
    assert message["action"] == "INFO"
    assert message["payload"] == {
        "kind": "operator_approval",
        "approval_id": approval["approval_id"],
        "text": "Approved: run the migration on staging.",
    }

    agent = TestClient(app)
    for path in (
        f"/managed/agent/sessions/{session_id}/operator-approvals/{approval['approval_id']}",
        f"/managed/agent/workspaces/team-one/sessions/{session_id}/operator-approvals/{approval['approval_id']}",
    ):
        verified = agent.get(path, headers={"Authorization": f"Bearer {token}"})
        assert verified.status_code == 200, verified.text
        assert verified.json() == {
            "valid": True,
            "approval_id": approval["approval_id"],
            "text": "Approved: run the migration on staging.",
            "created_at": approval["created_at"],
        }

    missing = agent.get(
        f"/managed/agent/sessions/{session_id}/operator-approvals/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404
    unauth = TestClient(app).get(
        f"/managed/agent/sessions/{session_id}/operator-approvals/{approval['approval_id']}"
    )
    assert unauth.status_code in {401, 403}


def test_operator_approval_is_scoped_to_its_session(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    other = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief-two", "title": "Other"},
    ).json()["workspace_session"]["session_id"]
    approval = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator-approvals",
        json={"text": "ok"},
    ).json()["approval"]
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    cross = TestClient(app).get(
        f"/managed/agent/sessions/{other}/operator-approvals/{approval['approval_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cross.status_code == 404


def test_operator_approval_requires_admin_and_text(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    anonymous = TestClient(app).post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator-approvals",
        json={"text": "ok"},
    )
    assert anonymous.status_code in {401, 403}
    empty = owner.post(
        f"/managed/workspaces/team-one/sessions/{session_id}/operator-approvals",
        json={"text": "   "},
    )
    assert empty.status_code == 422


# ── C9: panel-created owner is a human mediator ─────────────────────────────


def test_panel_created_owner_is_marked_human_mediator(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}").json()
    chief = next(item for item in detail["acp_session"]["members"] if item["agent_name"] == "chief")
    assert "human_mediator" in chief["capabilities"]
    assert chief["provider"] == "managed-web"


def test_agent_created_owner_is_not_human_mediator(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    app = _create_managed_app_with_spa(monkeypatch, _load_managed_app(), tmp_path)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    created = TestClient(app).post(
        "/managed/agent/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"agent_name": "codex-chief", "title": "Agent room"},
    )
    assert created.status_code == 200, created.text
    members = created.json()["acp_session"]["session"]["members"]
    assert "human_mediator" not in members[0]["capabilities"]


def test_agent_joining_with_owner_name_gets_clear_409(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    joined = TestClient(app).post(
        f"/managed/agent/sessions/{session_id}/join",
        headers={"Authorization": f"Bearer {token}"},
        json={"agent_name": "chief"},
    )
    assert joined.status_code == 409
    assert "taken by the session owner" in joined.json()["detail"]
    assert "already attached" in joined.json()["detail"]


# ── C12: permanent rooms ────────────────────────────────────────────────────


def test_permanent_room_blocks_agent_close_and_restricts_declared_members(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    app = _create_managed_app_with_spa(monkeypatch, _load_managed_app(), tmp_path)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)
    created = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={
            "agent_name": "jefe-del-panel",
            "title": "Proyecto A",
            "permanent": True,
            "declared_members": ["claude-a", "codex-b", "claude-a"],
        },
    )
    assert created.status_code == 200, created.text
    record = created.json()["workspace_session"]
    assert record["permanent"] is True
    assert record["declared_members"] == ["claude-a", "codex-b"]
    session_id = record["session_id"]
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    headers = {"Authorization": f"Bearer {token}"}

    stranger = TestClient(app).post(
        f"/managed/agent/sessions/{session_id}/join", headers=headers, json={"agent_name": "intruder"}
    )
    assert stranger.status_code == 403
    assert "claude-a" in stranger.json()["detail"]
    declared = TestClient(app).post(
        f"/managed/agent/sessions/{session_id}/join", headers=headers, json={"agent_name": "claude-a"}
    )
    assert declared.status_code == 200, declared.text

    close = TestClient(app).post(f"/managed/agent/sessions/{session_id}/close", headers=headers)
    assert close.status_code == 403
    assert "permanent" in close.json()["detail"]

    listed = owner.get("/managed/workspaces/team-one/sessions").json()["sessions"]
    assert listed[0]["permanent"] is True

    # Reversible: clearing the flag re-enables agent close.
    patched = owner.patch(
        f"/managed/workspaces/team-one/sessions/{session_id}",
        json={"permanent": False},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["workspace_session"]["permanent"] is False
    assert patched.json()["workspace_session"]["declared_members"] == ["claude-a", "codex-b"]
    close = TestClient(app).post(f"/managed/agent/sessions/{session_id}/close", headers=headers)
    assert close.status_code == 200, close.text


def test_permanent_room_survives_stale_cleanup(monkeypatch, tmp_path) -> None:
    import asyncio

    password = _bootstrap_env(monkeypatch, tmp_path)
    app = _create_managed_app_with_spa(monkeypatch, _load_managed_app(), tmp_path)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)
    session_id = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "jefe-del-panel", "permanent": True},
    ).json()["workspace_session"]["session_id"]
    coordination = app.state.managed_router_deps.runtime.coordination
    coordination._last_cleanup_at = None
    asyncio.run(coordination.cleanup_stale_sessions())
    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}").json()
    assert detail["workspace_session"]["live_status"] == "active"


def test_default_room_is_not_permanent(monkeypatch, tmp_path) -> None:
    app, owner, session_id = _owner_with_session(monkeypatch, tmp_path)
    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}").json()
    assert detail["workspace_session"]["permanent"] is False
    assert detail["workspace_session"]["declared_members"] == []


# ── A2/A3: token share prompts ──────────────────────────────────────────────


def test_token_bootstrap_offers_short_and_full_share_prompts_labeled_secret(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    app = _create_managed_app_with_spa(monkeypatch, _load_managed_app(), tmp_path)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)
    bootstrap = owner.post("/managed/workspaces/team-one/token/rotate").json()["bootstrap"]
    full = bootstrap["share_prompt"]
    short = bootstrap["share_prompt_short"]
    for prompt in (full, short):
        assert "secreto" in prompt
        assert "operator_approval" in prompt
        assert "--code-env" in prompt
        assert "--allow-tracked-repo" not in prompt
    assert "/downloads/ACP_AGENT.json" in full
    assert "/downloads/ACP_AGENT.json" not in short
    assert len(short) < len(full)
