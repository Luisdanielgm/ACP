"""Room prompt (session instructions) — M3 slice 1.

The workspace owner creates a session with a prompt; agents entering the room
receive it. The prompt rides in the managed workspace session record, so it is
delivered both to the dashboard (owner) and to agents (Bearer) via
_sanitize_workspace_session.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from test_managed_app_smoke import (
    _login_workspace_admin,
    _bootstrap_env,
    _create_managed_app_with_spa,
    _load_managed_app,
)

from acp_managed.auth.sqlite_store import ManagedWorkspaceSessionRecord
from acp_managed.routing._helpers import _sanitize_workspace_session


def test_sanitize_workspace_session_includes_prompt() -> None:
    record = ManagedWorkspaceSessionRecord(
        session_id="s1",
        workspace_id="w1",
        created_by_email="admin@example.com",
        owner_agent_name="chief",
        owner_member_token=None,
        title="Sprint",
        project="ACP",
        created_at="2026-01-01T00:00:00Z",
        prompt="Room rules: be concise.",
    )

    payload = _sanitize_workspace_session(record)

    assert payload["prompt"] == "Room rules: be concise."


def test_owner_creates_session_with_prompt_and_agent_receives_it(monkeypatch, tmp_path) -> None:
    password = _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    app = _create_managed_app_with_spa(monkeypatch, module, tmp_path)

    admin = TestClient(app)
    owner = TestClient(app)
    _login_workspace_admin(owner, password)

    prompt = "Sala AeroCostos. Reglas: responder en JSON y ser conciso."

    # Owner creates the room WITH a prompt.
    created = owner.post(
        "/managed/workspaces/team-one/sessions",
        json={"agent_name": "chief", "title": "Sprint", "prompt": prompt},
    )
    assert created.status_code == 200, created.text
    session_payload = created.json()["workspace_session"]
    assert session_payload["prompt"] == prompt
    session_id = session_payload["session_id"]

    # Owner sees the prompt in the dashboard session detail.
    detail = owner.get(f"/managed/workspaces/team-one/sessions/{session_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["workspace_session"]["prompt"] == prompt

    # An agent holding the workspace token receives the prompt when it enters the room.
    token = owner.post("/managed/workspaces/team-one/token/rotate").json()["raw_token"]
    agent_view = admin.get(
        f"/managed/agent/workspaces/team-one/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_view.status_code == 200, agent_view.text
    assert agent_view.json()["workspace_session"]["prompt"] == prompt
