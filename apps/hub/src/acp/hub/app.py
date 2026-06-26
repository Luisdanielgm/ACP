"""FastAPI app wiring for ACP hub websocket and HTTP compatibility endpoints."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from acp.hub.auth_service import AuthService, PermissiveAuthService
from acp.hub.bundle_archive import ACP_AGENT_BUNDLE_PATH, ACP_AGENT_SOURCE_DIR, ensure_bundle_archive
from acp.hub.bundle_release import build_bundle_release_manifest
from acp.hub.coordination_service import SessionCoordinationService
from acp.hub.coordination_store import SqliteCoordinationStore
from acp.hub.dashboard_auth import DashboardSessionStore
from acp.hub.downloads_html import render_downloads_html
from acp.hub.event_store import EventStore, InMemoryEventStore
from acp.hub.http_api import build_http_router
from acp.hub.landing_html import render_landing_html
from acp.hub.migrations import MigrationError, apply_sqlite_migrations, verify_sqlite_bootstrap_state
from acp.hub.session_registry import SessionRegistry
from acp.hub.sqlite_event_store import SqliteEventStore
from acp.hub.ws_ingress import run_ws_ingress
from acp.protocol.models import MAX_PAYLOAD_BYTES

_DEFAULT_MAX_PAYLOAD_BYTES = MAX_PAYLOAD_BYTES
_DEFAULT_PERSISTENCE_BACKEND = "sqlite"
_SUPPORTED_PERSISTENCE_BACKENDS = {"memory", "sqlite"}
_DEFAULT_SQLITE_PATH = ".planning/acp.sqlite3"
_TRUTHY = {"1", "true", "yes", "on"}

logger = logging.getLogger("acp.hub")


@dataclass
class HubRuntime:
    """In-memory runtime shared by websocket ingress and HTTP adapters."""

    active_agents: dict[str, Any] = field(default_factory=dict)
    trace_sink: list[dict[str, Any]] = field(default_factory=list)
    required_token: str | None = None
    max_payload_bytes: int = _DEFAULT_MAX_PAYLOAD_BYTES
    event_store: EventStore | None = None
    auth_service: AuthService | None = None
    auth_enforce: bool = False
    persistence_strict: bool = False
    token_overlap_until: str | None = None
    token_rotation_active: bool = False
    storage_ready: bool = True
    auth_ready: bool = True
    migration_ready: bool = True
    public_web_enabled: bool = True
    legacy_dashboard_enabled: bool = True
    # Whether coordination sessions survive a Hub restart/redeploy. False means
    # the in-memory store is in use and every session/member is wiped on restart.
    coordination_durable: bool = False
    # True when the in-memory backend was selected on purpose: a redeploy wipes
    # all state, so /runtime surfaces this footgun for ops visibility.
    memory_backend_warning: bool = False
    registry: SessionRegistry = field(init=False)
    coordination: SessionCoordinationService = field(default_factory=SessionCoordinationService)
    dashboard_sessions: DashboardSessionStore = field(default_factory=DashboardSessionStore)

    def __post_init__(self) -> None:
        if self.event_store is None:
            self.event_store = InMemoryEventStore()
        if self.auth_service is None:
            self.auth_service = PermissiveAuthService(
                required_token=self.required_token,
                scope_provider=_scope_provider_from_store(self.event_store),
                auth_enforce=self.auth_enforce,
            )
        self.registry = SessionRegistry(active_agents=self.active_agents)

    def snapshot_agents(self) -> list[str]:
        return self.registry.snapshot_agents()

    def trace_count(self) -> int:
        return len(self.trace_sink)

    def clear_traces(self) -> None:
        self.trace_sink.clear()

    def as_status_payload(self) -> dict[str, Any]:
        return {
            "agents": len(self.snapshot_agents()),
            "traces": self.trace_count(),
            "token_required": self.required_token is not None,
            "max_payload_bytes": self.max_payload_bytes,
            "storage_ready": self.storage_ready,
            "auth_ready": self.auth_ready,
            "migration_ready": self.migration_ready,
            "auth_enforce": self.auth_enforce,
            "persistence_strict": self.persistence_strict,
            "token_rotation_active": self.token_rotation_active,
            "token_overlap_until": self.token_overlap_until,
            "dashboard_sessions": self.dashboard_sessions.count(),
            "public_web_enabled": self.public_web_enabled,
            "legacy_dashboard_enabled": self.legacy_dashboard_enabled,
            "coordination_durable": self.coordination_durable,
            "memory_backend_warning": self.memory_backend_warning,
        }


def _token_from_env() -> str | None:
    token = os.getenv("ACP_TOKEN")
    if token is None:
        return None
    cleaned = token.strip()
    return cleaned if cleaned else None


def _max_payload_from_env() -> int:
    configured = os.getenv("ACP_MAX_PAYLOAD_BYTES")
    if configured is None:
        return _DEFAULT_MAX_PAYLOAD_BYTES

    try:
        parsed = int(configured.strip())
    except ValueError:
        return _DEFAULT_MAX_PAYLOAD_BYTES

    if parsed < 1024:
        return _DEFAULT_MAX_PAYLOAD_BYTES

    return parsed


def _resolve_version() -> str:
    configured = os.getenv("ACP_VERSION")
    if configured is None:
        return "0.1.0"
    cleaned = configured.strip()
    return cleaned if cleaned else "0.1.0"


def _persistence_backend_from_env() -> str:
    configured = os.getenv("ACP_PERSISTENCE_BACKEND")
    if configured is None:
        return _DEFAULT_PERSISTENCE_BACKEND
    cleaned = configured.strip().lower()
    if not cleaned:
        return _DEFAULT_PERSISTENCE_BACKEND
    if cleaned not in _SUPPORTED_PERSISTENCE_BACKENDS:
        supported = ", ".join(sorted(_SUPPORTED_PERSISTENCE_BACKENDS))
        raise RuntimeError(f"unsupported ACP_PERSISTENCE_BACKEND '{cleaned}'. supported: {supported}")
    return cleaned


def _sqlite_path_from_env() -> str:
    configured = os.getenv("ACP_SQLITE_PATH")
    if configured is None:
        return _DEFAULT_SQLITE_PATH
    cleaned = configured.strip()
    return cleaned if cleaned else _DEFAULT_SQLITE_PATH


def _auth_enforce_from_env() -> bool:
    configured = os.getenv("ACP_AUTH_ENFORCE")
    if configured is None:
        return False
    return configured.strip().lower() in _TRUTHY


def _persistence_strict_from_env() -> bool:
    configured = os.getenv("ACP_PERSISTENCE_STRICT")
    if configured is None:
        return False
    return configured.strip().lower() in _TRUTHY


def _public_web_enabled_from_env() -> bool:
    configured = os.getenv("ACP_PUBLIC_WEB_ENABLED")
    if configured is None:
        return True
    return configured.strip().lower() in _TRUTHY


def _legacy_dashboard_enabled_from_env() -> bool:
    configured = os.getenv("ACP_LEGACY_DASHBOARD_ENABLED")
    if configured is None:
        return True
    return configured.strip().lower() in _TRUTHY


def _token_previous_from_env() -> str | None:
    token = os.getenv("ACP_TOKEN_PREVIOUS")
    if token is None:
        return None
    cleaned = token.strip()
    return cleaned if cleaned else None


def _token_overlap_until_from_env() -> datetime | None:
    configured = os.getenv("ACP_TOKEN_OVERLAP_UNTIL")
    if configured is None:
        return None
    cleaned = configured.strip()
    if not cleaned:
        return None
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError("invalid ACP_TOKEN_OVERLAP_UNTIL; expected RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise RuntimeError("invalid ACP_TOKEN_OVERLAP_UNTIL; timezone offset is required")
    return parsed.astimezone(timezone.utc)


def _bootstrap_migrations_for_backend(*, persistence_backend: str) -> bool:
    if persistence_backend != "sqlite":
        return True
    sqlite_path = _sqlite_path_from_env()
    apply_sqlite_migrations(sqlite_path=sqlite_path)
    verify_sqlite_bootstrap_state(sqlite_path=sqlite_path)
    return True


def _scope_provider_from_store(event_store: EventStore | None) -> Any | None:
    if event_store is None:
        return None
    if hasattr(event_store, "get_scopes_for_principal"):
        return event_store
    return None


def create_runtime_from_env() -> HubRuntime:
    required_token = _token_from_env()
    previous_token = _token_previous_from_env()
    overlap_until = _token_overlap_until_from_env()
    if previous_token is not None and required_token is None:
        raise RuntimeError("ACP_TOKEN_PREVIOUS requires ACP_TOKEN")
    if previous_token is not None and overlap_until is None:
        raise RuntimeError("ACP_TOKEN_PREVIOUS requires ACP_TOKEN_OVERLAP_UNTIL")
    if previous_token is None and overlap_until is not None:
        raise RuntimeError("ACP_TOKEN_OVERLAP_UNTIL requires ACP_TOKEN_PREVIOUS")
    max_payload = _max_payload_from_env()
    persistence_backend = _persistence_backend_from_env()
    auth_enforce = _auth_enforce_from_env()
    persistence_strict = _persistence_strict_from_env()
    public_web_enabled = _public_web_enabled_from_env()
    legacy_dashboard_enabled = _legacy_dashboard_enabled_from_env()

    selected_store: EventStore
    sqlite_path = _sqlite_path_from_env()
    if persistence_backend == "sqlite":
        selected_store = SqliteEventStore(sqlite_path=sqlite_path)
    else:
        selected_store = InMemoryEventStore()

    runtime = HubRuntime(
        required_token=required_token,
        max_payload_bytes=max_payload,
        event_store=selected_store,
        coordination=(
            SessionCoordinationService(store=SqliteCoordinationStore(sqlite_path=sqlite_path))
            if persistence_backend == "sqlite"
            else SessionCoordinationService()
        ),
        auth_enforce=auth_enforce,
        persistence_strict=persistence_strict,
        public_web_enabled=public_web_enabled,
        legacy_dashboard_enabled=legacy_dashboard_enabled,
        token_overlap_until=(
            overlap_until.isoformat(timespec="seconds").replace("+00:00", "Z")
            if overlap_until is not None
            else None
        ),
        token_rotation_active=bool(
            required_token is not None
            and
            previous_token is not None
            and overlap_until is not None
            and datetime.now(timezone.utc) <= overlap_until
        ),
        auth_service=PermissiveAuthService(
            required_token=required_token,
            scope_provider=_scope_provider_from_store(selected_store),
            auth_enforce=auth_enforce,
            previous_token=previous_token,
            overlap_until=overlap_until,
        ),
    )
    runtime.storage_ready = persistence_backend in _SUPPORTED_PERSISTENCE_BACKENDS
    # Only the sqlite backend persists coordination sessions across restarts.
    # When this is False, a redeploy wipes every live session/member binding.
    runtime.coordination_durable = persistence_backend == "sqlite"
    runtime.memory_backend_warning = persistence_backend == "memory"
    if runtime.memory_backend_warning:
        logger.warning(
            "ACP_PERSISTENCE_BACKEND=memory: coordination state is in-memory only "
            "and EVERY session/member binding is wiped on restart/redeploy. "
            "Set ACP_PERSISTENCE_BACKEND=sqlite (the default) for durable persistence."
        )
    runtime.auth_ready = runtime.auth_service is not None
    try:
        runtime.migration_ready = _bootstrap_migrations_for_backend(
            persistence_backend=persistence_backend
        )
    except MigrationError as exc:
        runtime.migration_ready = False
        raise RuntimeError(f"phase-6 migration bootstrap failed: {exc}") from exc
    return runtime


def _register_ws_endpoint(app: FastAPI, runtime: HubRuntime) -> None:
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        session_id = f"ws:{uuid4()}"
        await run_ws_ingress(
            websocket,
            session_id=session_id,
            active_agents=runtime.active_agents,
            trace_sink=runtime.trace_sink,
            session_registry=runtime.registry,
            auth_service=runtime.auth_service,
            event_store=runtime.event_store,
            max_payload_bytes=runtime.max_payload_bytes,
            persistence_strict=runtime.persistence_strict,
        )


def _register_runtime_endpoint(app: FastAPI, runtime: HubRuntime) -> None:
    @app.get("/runtime")
    async def runtime_payload() -> dict[str, Any]:
        return {
            "service": "acp-hub",
            "status": "ok",
            "runtime": runtime.as_status_payload(),
        }


def _register_public_web_endpoints(app: FastAPI, runtime: HubRuntime) -> None:
    @app.get("/", response_class=HTMLResponse)
    @app.head("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        return HTMLResponse(content=render_landing_html(build_bundle_release_manifest(base_url=str(request.base_url))))

    @app.get("/downloads", response_class=HTMLResponse)
    async def downloads_page(request: Request) -> HTMLResponse:
        release = build_bundle_release_manifest(base_url=str(request.base_url))
        return HTMLResponse(content=render_downloads_html(release))

    @app.get("/downloads/ACP_AGENT.json")
    async def download_bundle_manifest(request: Request) -> JSONResponse:
        return JSONResponse(content=build_bundle_release_manifest(base_url=str(request.base_url)))

    @app.get("/downloads/ACP_AGENT.zip")
    async def download_bundle() -> FileResponse:
        bundle_path = ensure_bundle_archive()
        if not bundle_path.is_file():
            raise HTTPException(status_code=404, detail="ACP_AGENT.zip is not available.")
        return FileResponse(
            path=bundle_path,
            media_type="application/zip",
            filename="ACP_AGENT.zip",
        )

    @app.get("/downloads/ACP_AGENT/AGENT.md")
    async def download_agent_guide() -> FileResponse:
        guide_path = ACP_AGENT_SOURCE_DIR / "AGENT.md"
        if not guide_path.is_file():
            raise HTTPException(status_code=404, detail="ACP_AGENT/AGENT.md is not available.")
        return FileResponse(
            path=guide_path,
            media_type="text/markdown; charset=utf-8",
            filename="AGENT.md",
        )

    @app.get("/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md")
    async def download_agent_skill() -> FileResponse:
        skill_path = ACP_AGENT_SOURCE_DIR / "skills" / "acp-session-coordinator" / "SKILL.md"
        if not skill_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="ACP_AGENT/skills/acp-session-coordinator/SKILL.md is not available.",
            )
        return FileResponse(
            path=skill_path,
            media_type="text/markdown; charset=utf-8",
            filename="SKILL.md",
        )


_PUBLIC_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static" / "public"


def _vue_views_from_env() -> set[str]:
    configured = os.getenv("ACP_VUE_VIEWS", "")
    if not configured.strip():
        return set()
    if configured.strip().lower() == "all":
        return {"all"}
    return {v.strip().lower() for v in configured.split(",") if v.strip()}


def _register_vue_spa_fallback(app: FastAPI, vue_views: set[str]) -> None:
    if not _PUBLIC_STATIC_DIR.is_dir():
        return
    assets_dir = _PUBLIC_STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="public-assets")

    index_html = _PUBLIC_STATIC_DIR / "index.html"
    if not index_html.is_file():
        return

    spa_routes = {"/", "/downloads", "/dashboard", "/dashboard/session"}

    if "all" in vue_views:
        for route in spa_routes:
            _register_spa_route(app, route, index_html)


def _register_spa_route(app: FastAPI, path: str, index_html: Path) -> None:
    @app.get(path, response_class=HTMLResponse, include_in_schema=False)
    async def _spa_fallback() -> HTMLResponse:
        return HTMLResponse(content=index_html.read_text(encoding="utf-8"))

    _spa_fallback.__name__ = f"spa_{path.strip('/').replace('/', '_') or 'root'}"


def _register_release_api(app: FastAPI) -> None:
    @app.get("/api/release")
    async def api_release(request: Request) -> JSONResponse:
        return JSONResponse(content=build_bundle_release_manifest(base_url=str(request.base_url)))


def create_app(*, runtime: HubRuntime | None = None) -> FastAPI:
    runtime_instance = runtime or create_runtime_from_env()
    ensure_bundle_archive(bundle_path=ACP_AGENT_BUNDLE_PATH)

    app = FastAPI(
        title="ACP Hub",
        version=_resolve_version(),
    )
    app.state.runtime = runtime_instance

    app.include_router(
        build_http_router(
            runtime_instance,
            legacy_dashboard_enabled=runtime_instance.legacy_dashboard_enabled,
        )
    )
    _register_ws_endpoint(app, runtime_instance)
    _register_runtime_endpoint(app, runtime_instance)
    _register_release_api(app)

    vue_views = _vue_views_from_env()

    if runtime_instance.public_web_enabled and "all" not in vue_views:
        _register_public_web_endpoints(app, runtime_instance)

    _register_vue_spa_fallback(app, vue_views)

    return app


app = create_app()
