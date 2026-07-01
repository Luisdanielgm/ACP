from __future__ import annotations

import hashlib
import importlib
import sys

from fastapi.testclient import TestClient


def _load_managed_app():
    sys.modules.pop("acp_managed.app", None)
    return importlib.import_module("acp_managed.app")


def _bootstrap_env(monkeypatch, tmp_path) -> str:
    password = "admin-pass"
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "agent-secret")
    monkeypatch.delenv("ACP_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("ACP_PRIVATE_OPERATOR_ENABLED", raising=False)
    monkeypatch.delenv("ACP_MANAGED_WHITELIST", raising=False)
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))
    monkeypatch.setenv("ACP_WORKSPACE_SLUG", "team-one")
    monkeypatch.setenv("ACP_WORKSPACE_NAME", "Team One")
    monkeypatch.setenv("ACP_WORKSPACE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ACP_WORKSPACE_ADMIN_PASSWORD_HASH", password_hash)
    return password


def test_managed_overlay_serves_frontend_dist_fallback(monkeypatch, tmp_path) -> None:
    _bootstrap_env(monkeypatch, tmp_path)
    module = _load_managed_app()

    dist_dir = tmp_path / "frontend" / "packages" / "managed-app" / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!doctype html><html><body><div id='app'>fallback</div></body></html>",
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('fallback');", encoding="utf-8")

    monkeypatch.setattr("acp_managed.ui.spa._MANAGED_STATIC_DIR_CANDIDATES", (tmp_path / "static" / "managed", dist_dir))

    client = TestClient(module.create_managed_app())

    response = client.get("/managed/login")
    assert response.status_code == 200
    assert "fallback" in response.text

    asset_response = client.get("/managed/assets/app.js")
    assert asset_response.status_code == 200
    assert "fallback" in asset_response.text


def test_managed_overlay_serves_static_dir_from_process_cwd(monkeypatch, tmp_path) -> None:
    _bootstrap_env(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    module = _load_managed_app()

    static_dir = tmp_path / "static" / "managed"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body><div id='app'>cwd static</div></body></html>",
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('cwd static');", encoding="utf-8")

    monkeypatch.setattr("acp_managed.ui.spa._MANAGED_STATIC_DIR_CANDIDATES", ())

    client = TestClient(module.create_managed_app())

    response = client.get("/")
    assert response.status_code == 200
    assert "cwd static" in response.text

    asset_response = client.get("/managed/assets/app.js")
    assert asset_response.status_code == 200
    assert "cwd static" in asset_response.text
