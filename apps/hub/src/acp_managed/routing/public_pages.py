"""Public / anonymous page routes (SPA shells) — de-tangle slice 2a.

These routes only return the managed SPA shell; authentication happens
client-side. They take no router deps yet (anonymous), but accept the deps
bundle to keep a uniform build_*_router(deps) factory signature.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from acp_managed.routing import ManagedRouterDeps
from acp_managed.ui.spa import _managed_spa_response


def build_public_pages_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def managed_home() -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/downloads", response_class=HTMLResponse)
    async def managed_downloads(request: Request) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/dashboard/session", response_class=HTMLResponse)
    async def managed_session_dashboard_page() -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/login", response_class=HTMLResponse)
    async def managed_login_page(error: str | None = None) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/invitations/{token}", response_class=HTMLResponse)
    async def managed_workspace_invitation_page(token: str, request: Request) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/dashboard", response_class=HTMLResponse)
    async def managed_dashboard(acp_managed_session: str | None = Cookie(default=None)) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/ui/workspaces", response_class=HTMLResponse)
    async def managed_my_workspaces_page(acp_managed_session: str | None = Cookie(default=None)) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/admin/workspaces/ui", response_class=HTMLResponse)
    async def managed_workspaces_admin_page(acp_managed_session: str | None = Cookie(default=None)) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/ui/workspaces/{slug}", response_class=HTMLResponse)
    async def managed_workspace_dashboard_page(slug: str, acp_managed_session: str | None = Cookie(default=None)) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/ui/workspaces/{slug}/sessions", response_class=HTMLResponse)
    async def managed_workspace_sessions_page(slug: str, acp_managed_session: str | None = Cookie(default=None)) -> HTMLResponse:
        return _managed_spa_response()

    @router.get("/managed/ui/workspaces/{slug}/sessions/{session_id}", response_class=HTMLResponse)
    async def managed_workspace_session_detail_page(
        slug: str,
        session_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        return _managed_spa_response()

    return router
