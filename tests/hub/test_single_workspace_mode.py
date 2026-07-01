from __future__ import annotations

import hashlib
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from acp_managed.auth.sqlite_store import ManagedWorkspace, SqliteManagedPrincipalStore
from acp_managed.auth.whitelist import ManagedPrincipal


def _password_hash(password: str = "admin-pass") -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _load_managed_app():
    sys.modules.pop("acp_managed.app", None)
    return importlib.import_module("acp_managed.app")


def _base_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "agent-secret")
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))


def _single_workspace_env(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.delenv("ACP_DEPLOYMENT_MODE", raising=False)
    monkeypatch.setenv("ACP_WORKSPACE_SLUG", "default")
    monkeypatch.setenv("ACP_WORKSPACE_NAME", "Default Workspace")
    monkeypatch.setenv("ACP_WORKSPACE_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("ACP_WORKSPACE_ADMIN_PASSWORD_HASH", _password_hash())


def _operator_env(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_DEPLOYMENT_MODE", "operator")
    monkeypatch.setenv("ACP_PRIVATE_OPERATOR_ENABLED", "true")
    monkeypatch.setenv(
        "ACP_MANAGED_WHITELIST",
        f"admin@example.com={_password_hash()}:instance_admin,active",
    )


def test_public_default_bootstraps_exactly_one_workspace_and_admin(monkeypatch, tmp_path) -> None:
    _single_workspace_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    client = TestClient(module.create_managed_app())

    store = client.app.state.managed_principal_store
    workspaces = store.list_workspaces()
    assert len(workspaces) == 1
    assert workspaces[0].slug == "default"
    assert store.get("owner@example.com").role == "workspace_admin"
    membership = store.get_membership(workspace_id=workspaces[0].workspace_id, email="owner@example.com")
    assert membership is not None
    assert membership.role == "workspace_admin"

    login = client.post(
        "/managed/auth/login",
        json={"email": "owner@example.com", "password": "admin-pass"},
    )
    assert login.status_code == 200
    assert login.json()["deployment_mode"] == "single_workspace"
    assert login.json()["default_workspace"]["slug"] == "default"
    assert login.json()["redirect_url"] == "/managed/ui/workspaces/default"

    session = client.get("/managed/auth/me")
    assert session.status_code == 200
    assert session.json()["deployment_mode"] == "single_workspace"
    assert session.json()["default_workspace"]["slug"] == "default"
    assert session.json()["redirect_url"] == "/managed/ui/workspaces/default"


def test_public_default_does_not_mount_global_workspace_admin_routes(monkeypatch, tmp_path) -> None:
    _single_workspace_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    client = TestClient(module.create_managed_app())

    response = client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-two", "name": "Team Two", "status": "active"},
    )
    assert response.status_code == 404


def test_single_workspace_mode_fails_fast_for_multi_workspace_database(monkeypatch, tmp_path) -> None:
    _single_workspace_env(monkeypatch, tmp_path)
    store = SqliteManagedPrincipalStore(sqlite_path=tmp_path / "acp-managed-auth.sqlite3")
    store.create(
        ManagedPrincipal(
            email="owner@example.com",
            password_hash=_password_hash(),
            role="workspace_admin",
            status="active",
        )
    )
    store.create_workspace(
        ManagedWorkspace(
            workspace_id="ws_one",
            slug="one",
            name="One",
            status="active",
            created_by="owner@example.com",
        )
    )
    store.create_workspace(
        ManagedWorkspace(
            workspace_id="ws_two",
            slug="two",
            name="Two",
            status="active",
            created_by="owner@example.com",
        )
    )

    with pytest.raises(RuntimeError, match="multiple workspaces"):
        _load_managed_app()


def test_operator_mode_requires_private_overlay_flag(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_DEPLOYMENT_MODE", "operator")
    monkeypatch.delenv("ACP_PRIVATE_OPERATOR_ENABLED", raising=False)

    with pytest.raises(ValueError, match="reserved for private overlays"):
        _load_managed_app()


def test_operator_mode_preserves_global_workspace_admin_routes(monkeypatch, tmp_path) -> None:
    _operator_env(monkeypatch, tmp_path)
    module = _load_managed_app()
    client = TestClient(module.create_managed_app())

    login = client.post(
        "/managed/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass"},
    )
    assert login.status_code == 200
    response = client.post(
        "/managed/admin/workspaces",
        json={"slug": "team-one", "name": "Team One", "status": "active"},
    )
    assert response.status_code == 200
