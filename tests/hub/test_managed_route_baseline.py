from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

BASELINE_PATH = Path(__file__).parent / "managed_routes_baseline.json"


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _bootstrap_managed_env(monkeypatch, tmp_path) -> None:
    password_hash = hashlib.sha256(b"admin-pass").hexdigest()
    monkeypatch.setenv("ACP_MANAGED_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "agent-secret")
    monkeypatch.setenv("ACP_DEPLOYMENT_MODE", "operator")
    monkeypatch.setenv("ACP_PUBLIC_WEB_ENABLED", "false")
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(tmp_path / "acp.sqlite3"))
    monkeypatch.setenv("ACP_MANAGED_AUTH_SQLITE_PATH", str(tmp_path / "acp-managed-auth.sqlite3"))
    monkeypatch.setenv(
        "ACP_MANAGED_WHITELIST",
        f"admin@example.com={password_hash}:instance_admin,active",
    )


def _build_managed_app(monkeypatch, tmp_path):
    _bootstrap_managed_env(monkeypatch, tmp_path)
    sys.modules.pop("acp_managed.app", None)
    module = importlib.import_module("acp_managed.app")
    return module.create_managed_app()


def _route_surface(app) -> list[dict]:
    routes = []
    for route in app.routes:
        methods = sorted(getattr(route, "methods", None) or [])
        routes.append({"path": getattr(route, "path", "?"), "methods": methods})
    routes.sort(key=lambda item: (item["path"], ",".join(item["methods"])))
    return routes


def test_managed_route_surface_matches_baseline(monkeypatch, tmp_path) -> None:
    # A-DETANGLE-00: freeze the managed app's route + app.state surface so any
    # de-tangle slice that drops, renames, or moves a route/state attribute fails
    # loudly. Regenerate the baseline ONLY for an intentional API change.
    baseline = _load_baseline()
    app = _build_managed_app(monkeypatch, tmp_path)

    current_routes = _route_surface(app)
    assert len(current_routes) == baseline["route_count"]
    assert current_routes == baseline["routes"]

    state_keys = sorted(vars(app.state).get("_state", {}).keys())
    assert state_keys == baseline["state_keys"]


def test_managed_router_deps_is_built_and_populated(monkeypatch, tmp_path) -> None:
    # A-DETANGLE-02: create_managed_app builds the ManagedRouterDeps bundle (the
    # router-factory seam) with every dependency populated. Routes still inline.
    from dataclasses import fields

    from acp_managed.routing import ManagedRouterDeps

    app = _build_managed_app(monkeypatch, tmp_path)
    deps = app.state.managed_router_deps

    assert isinstance(deps, ManagedRouterDeps)
    for field in fields(deps):
        assert getattr(deps, field.name) is not None, field.name
    assert deps.invitation_ttl_seconds > 0
    assert callable(deps.audit)
