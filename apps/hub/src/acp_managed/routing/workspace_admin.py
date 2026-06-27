"""Workspace-admin (browser-session) routes — de-tangle slice (A-DETANGLE-06).

The workspace_admin-facing surface, guarded by require_workspace_admin_access
(or current_principal_from_cookie for "my workspaces"): agent-token management,
team presets, the workspace dashboard, session-token rotate/revoke, and the
workspace session list/create/detail views.

Security note: these browser-admin responses intentionally include the
owner_member_token (include_owner_member_token=True) because the viewer is an
authenticated workspace admin. The agent (Bearer) router must NOT — see
A-DETANGLE-07. All dependencies come from the ManagedRouterDeps seam.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from acp_managed.auth.sqlite_store import ManagedWorkspaceSessionRecord
from acp_managed.contracts import (
    WORKSPACE_TEAM_PRESETS,
    CreateAgentTokenRequest,
    CreateWorkspacePresetRequest,
    CreateWorkspaceSessionRequest,
)
from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing._helpers import (
    _managed_agent_bootstrap_payload,
    _managed_session_aliases,
    _sanitize_agent_token,
    _sanitize_membership,
    _sanitize_workspace,
    _sanitize_workspace_admin_invitation,
    _sanitize_workspace_session,
    _session_dashboard_fallback_url,
    _session_dashboard_url,
)


def build_workspace_admin_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    principal_store = deps.principal_store
    runtime = deps.runtime
    _audit = deps.audit
    current_principal_from_cookie = deps.access_service.current_principal_from_cookie
    require_workspace_admin_access = deps.access_service.require_workspace_admin_access
    token_service = deps.token_service
    issue_workspace_agent_token = deps.token_service.issue_workspace_agent_token
    create_workspace_session_entry = deps.workspace_session_service.create_workspace_session_entry

    @router.get("/managed/workspaces")
    async def managed_my_workspaces(acp_managed_session: str | None = Cookie(default=None)) -> JSONResponse:
        principal = current_principal_from_cookie(acp_managed_session)
        memberships = principal_store.list_workspaces_for_email(email=principal.email)
        workspaces_by_id = {
            workspace.workspace_id: workspace
            for workspace in principal_store.list_workspaces()
        }
        items = []
        for membership in memberships:
            workspace = workspaces_by_id.get(membership.workspace_id)
            if workspace is None:
                continue
            items.append(
                {
                    "workspace": _sanitize_workspace(workspace),
                    "membership": _sanitize_membership(membership),
                    "sessions": [
                        _sanitize_workspace_session(item)
                        for item in principal_store.list_workspace_sessions(workspace_id=workspace.workspace_id)
                    ],
                }
            )
        return JSONResponse({"workspaces": items, "count": len(items)})

    @router.get("/managed/admin/workspaces/{slug}/agent-tokens")
    async def managed_list_agent_tokens(
        slug: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, _ = require_workspace_admin_access(slug=slug, acp_managed_session=acp_managed_session)
        records = principal_store.list_agent_tokens_for_workspace(workspace_id=workspace.workspace_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "agent_tokens": [_sanitize_agent_token(item) for item in records],
                "count": len(records),
            }
        )

    @router.post("/managed/admin/workspaces/{slug}/agent-tokens")
    async def managed_create_agent_token(
        slug: str,
        payload: CreateAgentTokenRequest,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        record, raw_token = issue_workspace_agent_token(
            workspace=workspace,
            created_by_email=acting_principal.email,
            agent_name=payload.agent_name,
            label=payload.label,
        )
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(record),
                "raw_token": raw_token,
                "bootstrap": _managed_agent_bootstrap_payload(
                    request=request,
                    workspace=workspace,
                    token_record=record,
                    raw_token=raw_token,
                ),
            }
        )

    @router.delete("/managed/admin/workspaces/{slug}/agent-tokens/{token_id}")
    async def managed_revoke_agent_token(
        slug: str,
        token_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, _ = require_workspace_admin_access(slug=slug, acp_managed_session=acp_managed_session)
        existing = principal_store.get_agent_token(token_id=token_id)
        if existing is None or existing.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed agent token does not exist")
        updated = principal_store.revoke_agent_token(token_id=token_id)
        return JSONResponse(
            {
                "status": "revoked",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(updated),
            }
        )

    @router.post("/managed/admin/workspaces/{slug}/presets/create")
    async def managed_create_workspace_preset(
        slug: str,
        payload: CreateWorkspacePresetRequest,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        preset = WORKSPACE_TEAM_PRESETS.get(payload.preset_id)
        if preset is None:
            raise HTTPException(status_code=404, detail="managed workspace preset does not exist")
        agents_raw: list[str] = preset["agents"]  # type: ignore[assignment]
        for agent_name in tuple(str(item) for item in agents_raw):
            issue_workspace_agent_token(
                workspace=workspace,
                created_by_email=acting_principal.email,
                agent_name=agent_name,
                label=None,
            )
        await create_workspace_session_entry(
            workspace=workspace,
            created_by_email=acting_principal.email,
            owner_agent_name=str(agents_raw[0]) if agents_raw else "",
            title=str(preset["title"]),
            project=workspace.name,
            resolve_name_conflicts=True,
        )
        return JSONResponse(
            {"status": "created", "preset_id": payload.preset_id, "title": str(preset["title"])}
        )

    @router.get("/managed/workspaces/{slug}")
    async def managed_workspace_dashboard(
        slug: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, membership = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        admin_membership = principal_store.get_workspace_admin_membership(workspace_id=workspace.workspace_id)
        invitations = principal_store.list_workspace_admin_invitations(workspace_id=workspace.workspace_id)
        active_token = principal_store.get_active_agent_token_for_workspace(workspace_id=workspace.workspace_id)
        sessions = principal_store.list_workspace_sessions(workspace_id=workspace.workspace_id)

        # Enrich each persisted workspace session with live coordination state
        # so the SPA can show "active / waiting / closed" without N+1 calls.
        live_by_id: dict[str, dict[str, object]] = {}
        try:
            snapshot = await runtime.coordination.dashboard_snapshot()
            for live_session in snapshot.get("sessions", []) or []:
                sid = live_session.get("session_id") if isinstance(live_session, dict) else None
                if isinstance(sid, str) and sid:
                    live_by_id[sid] = live_session
        except Exception:
            # If coordination is briefly unavailable we still return the
            # persisted list. The SPA must treat live_info absence as "unknown".
            live_by_id = {}

        def _enrich_session(record: ManagedWorkspaceSessionRecord) -> dict[str, object]:
            base = _sanitize_workspace_session(record, include_owner_member_token=True)
            live = live_by_id.get(record.session_id)
            if isinstance(live, dict):
                members = live.get("members")
                member_count = len(members) if isinstance(members, list) else None
                base["live_status"] = "active"
                base["member_count"] = member_count
                # Pass through coarse status counts when available so the card
                # can render "1 busy, 2 waiting" without a deeper query.
                status_counts = live.get("status_counts")
                if isinstance(status_counts, dict):
                    base["status_counts"] = status_counts
            else:
                base["live_status"] = "closed"
                base["member_count"] = None
            return base

        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "workspace_admin": _sanitize_membership(admin_membership) if admin_membership is not None else None,
                "viewer_membership": _sanitize_membership(membership) if membership is not None else None,
                "active_token": _sanitize_agent_token(active_token) if active_token is not None else None,
                "invitations": [_sanitize_workspace_admin_invitation(item) for item in invitations[:5]],
                "sessions": [_enrich_session(item) for item in sessions],
                "counts": {
                    "sessions": len(sessions),
                    "pending_invitations": len([item for item in invitations if item.status == "pending"]),
                },
            }
        )

    @router.post("/managed/workspaces/{slug}/token/rotate")
    async def managed_rotate_workspace_token(
        slug: str,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        record, raw_token = issue_workspace_agent_token(
            workspace=workspace,
            created_by_email=acting_principal.email,
            agent_name=None,
            label=f"{workspace.slug}-session-token",
        )
        _audit(
            request,
            "managed.workspace_token_rotated",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=workspace.workspace_id,
            metadata={"slug": workspace.slug, "token_id": record.token_id, "token_hint": record.token_hint},
        )
        return JSONResponse(
            {
                "status": "rotated",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(record),
                "raw_token": raw_token,
                "bootstrap": _managed_agent_bootstrap_payload(
                    request=request,
                    workspace=workspace,
                    token_record=record,
                    raw_token=raw_token,
                ),
            }
        )

    @router.post("/managed/workspaces/{slug}/token/revoke")
    async def managed_revoke_workspace_token(
        slug: str,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        updated = token_service.revoke_active_workspace_token(workspace=workspace)
        _audit(
            request,
            "managed.workspace_token_revoked",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=workspace.workspace_id,
            metadata={"slug": workspace.slug, "token_id": updated.token_id, "token_hint": updated.token_hint},
        )
        return JSONResponse(
            {
                "status": "revoked",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(updated),
            }
        )

    @router.get("/managed/workspaces/{slug}/sessions")
    async def managed_list_workspace_sessions(
        slug: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, _ = require_workspace_admin_access(slug=slug, acp_managed_session=acp_managed_session)
        records = principal_store.list_workspace_sessions(workspace_id=workspace.workspace_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "sessions": [
                    _sanitize_workspace_session(item, include_owner_member_token=True) for item in records
                ],
                "count": len(records),
            }
        )

    @router.post("/managed/workspaces/{slug}/sessions")
    async def managed_create_workspace_session(
        slug: str,
        payload: CreateWorkspaceSessionRequest,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        if not payload.agent_name.strip():
            raise HTTPException(status_code=422, detail="agent_name is required")
        record, result = await create_workspace_session_entry(
            workspace=workspace,
            created_by_email=principal.email,
            owner_agent_name=payload.agent_name.strip(),
            title=payload.title.strip() if isinstance(payload.title, str) and payload.title.strip() else None,
            project=payload.project.strip() if isinstance(payload.project, str) and payload.project.strip() else None,
            prompt=payload.prompt,
            capabilities=payload.capabilities,
            resolve_name_conflicts=True,
        )
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "acp_session": result,
                **_managed_session_aliases(record=record, acp_session=result),
            }
        )

    @router.post("/managed/ui/workspaces/{slug}/sessions/create")
    async def managed_create_workspace_session_form(
        slug: str,
        request: Request,
        agent_name: str = Form(...),
        title: str = Form(default=""),
        project: str = Form(default=""),
        acp_managed_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        principal, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        if not agent_name.strip():
            raise HTTPException(status_code=422, detail="agent_name is required")
        record, result = await create_workspace_session_entry(
            workspace=workspace,
            created_by_email=principal.email,
            owner_agent_name=agent_name.strip(),
            title=title.strip() or None,
            project=project.strip() or None,
            resolve_name_conflicts=True,
        )
        return RedirectResponse(
            url=f"/managed/ui/workspaces/{urllib.parse.quote(slug, safe='')}/sessions/{urllib.parse.quote(str(result['session_id']), safe='')}",
            status_code=303,
        )

    @router.get("/managed/ui/workspaces/{slug}/sessions/{session_id}/live")
    async def managed_workspace_session_live_redirect(
        slug: str,
        session_id: str,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> RedirectResponse:
        _, workspace, _ = require_workspace_admin_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        if record.owner_member_token:
            target_url = _session_dashboard_url(
                request=request,
                session_id=record.session_id,
                agent_name=record.owner_agent_name,
                member_token=record.owner_member_token,
            )
        else:
            target_url = _session_dashboard_fallback_url(
                request=request,
                session_id=record.session_id,
            )
        return RedirectResponse(url=target_url, status_code=307)

    @router.get("/managed/workspaces/{slug}/sessions/{session_id}")
    async def managed_workspace_session_detail(
        slug: str,
        session_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, _ = require_workspace_admin_access(slug=slug, acp_managed_session=acp_managed_session)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        try:
            session_detail = await runtime.coordination.session_detail(
                session_id=session_id,
                include_join_code=True,
            )
        except Exception:
            session_detail = None
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "acp_session": session_detail,
                **_managed_session_aliases(
                    record=record,
                    acp_session=session_detail if isinstance(session_detail, dict) else None,
                ),
            }
        )

    return router
