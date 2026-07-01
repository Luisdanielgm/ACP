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
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Cookie, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from acp.hub.coordination_service import SessionAccessError, SessionNotFoundError
from acp_managed.auth.sqlite_store import ManagedWorkspaceSessionRecord
from acp_managed.contracts import (
    WORKSPACE_TEAM_PRESETS,
    CreateAgentTokenRequest,
    CreateRoomWallPostRequest,
    CreateWorkspacePresetRequest,
    SendRoomOperatorMessageRequest,
    CreateWorkspaceSessionRequest,
    UpdateRoomWallPostRequest,
)
from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing._helpers import (
    _managed_agent_bootstrap_payload,
    _managed_session_aliases,
    _sanitize_agent_token,
    _sanitize_membership,
    _sanitize_room_file,
    _sanitize_room_wall_post,
    _sanitize_workspace,
    _sanitize_workspace_admin_invitation,
    _sanitize_workspace_session,
    _session_dashboard_fallback_url,
    _session_dashboard_url,
)


_MAX_ROOM_FILE_BYTES = 256 * 1024
_MAX_ROOM_FILES = 20
_MAX_ROOM_TOTAL_BYTES = 1024 * 1024


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

    @router.get("/managed/workspaces/{slug}/agent-tokens")
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

    @router.post("/managed/workspaces/{slug}/agent-tokens")
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

    @router.delete("/managed/workspaces/{slug}/agent-tokens/{token_id}")
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

    @router.post("/managed/workspaces/{slug}/presets/create")
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

    def _require_workspace_session_record(
        *,
        slug: str,
        session_id: str,
        acp_managed_session: str | None,
    ) -> tuple[object, object, ManagedWorkspaceSessionRecord]:
        principal, workspace, _ = require_workspace_admin_access(slug=slug, acp_managed_session=acp_managed_session)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        return principal, workspace, record

    @router.get("/managed/workspaces/{slug}/sessions/{session_id}/wall")
    async def managed_workspace_session_wall(
        slug: str,
        session_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        posts = principal_store.list_room_wall_posts(session_id=record.session_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "posts": [_sanitize_room_wall_post(item) for item in posts],
                "count": len(posts),
            }
        )

    @router.post("/managed/workspaces/{slug}/sessions/{session_id}/wall")
    async def managed_create_workspace_session_wall_post(
        slug: str,
        session_id: str,
        payload: CreateRoomWallPostRequest,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        principal, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        post = principal_store.create_room_wall_post(
            session_id=record.session_id,
            workspace_id=workspace.workspace_id,
            author_type="owner",
            author_name=principal.email,
            body=payload.body,
            pinned=payload.pinned,
        )
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "post": _sanitize_room_wall_post(post),
            }
        )

    @router.patch("/managed/workspaces/{slug}/sessions/{session_id}/wall/{post_id}")
    async def managed_pin_workspace_session_wall_post(
        slug: str,
        session_id: str,
        post_id: str,
        payload: UpdateRoomWallPostRequest,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        existing = principal_store.get_room_wall_post(post_id=post_id)
        if existing is None or existing.session_id != record.session_id or existing.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="wall post does not exist")
        post = principal_store.set_room_wall_post_pinned(post_id=post_id, pinned=payload.pinned)
        return JSONResponse(
            {
                "status": "updated",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "post": _sanitize_room_wall_post(post),
            }
        )

    @router.delete("/managed/workspaces/{slug}/sessions/{session_id}/wall/{post_id}")
    async def managed_delete_workspace_session_wall_post(
        slug: str,
        session_id: str,
        post_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        existing = principal_store.get_room_wall_post(post_id=post_id)
        if existing is None or existing.session_id != record.session_id or existing.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="wall post does not exist")
        deleted = principal_store.delete_room_wall_post(post_id=post_id)
        return JSONResponse(
            {
                "status": "deleted" if deleted else "not_found",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "post_id": post_id,
            }
        )

    async def _read_room_file_upload(file: UploadFile) -> bytes:
        content = await file.read(_MAX_ROOM_FILE_BYTES + 1)
        if len(content) > _MAX_ROOM_FILE_BYTES:
            raise HTTPException(status_code=413, detail="room file exceeds 256 KiB limit")
        if not content:
            raise HTTPException(status_code=422, detail="room file must not be empty")
        return content

    def _room_file_download_response(file_record) -> Response:
        quoted_name = urllib.parse.quote(file_record.filename, safe="")
        return Response(
            content=file_record.content,
            media_type=file_record.content_type,
            headers={"content-disposition": f"attachment; filename*=UTF-8''{quoted_name}"},
        )

    def _room_file_quota_payload(files) -> dict[str, int]:
        total_bytes = sum(item.size_bytes for item in files)
        return {
            "count": len(files),
            "total_bytes": total_bytes,
            "max_file_bytes": _MAX_ROOM_FILE_BYTES,
            "max_files": _MAX_ROOM_FILES,
            "max_total_bytes": _MAX_ROOM_TOTAL_BYTES,
            "remaining_files": max(_MAX_ROOM_FILES - len(files), 0),
            "remaining_bytes": max(_MAX_ROOM_TOTAL_BYTES - total_bytes, 0),
        }

    def _require_room_file_quota(files, *, next_size_bytes: int) -> None:
        quota = _room_file_quota_payload(files)
        if quota["count"] >= _MAX_ROOM_FILES:
            raise HTTPException(status_code=409, detail="room file count quota exceeded")
        if quota["total_bytes"] + next_size_bytes > _MAX_ROOM_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="room file total bytes quota exceeded")

    def _normalize_room_file_purpose(purpose: str) -> str:
        normalized = purpose.strip().lower() if isinstance(purpose, str) else "artifact"
        if normalized not in {"artifact", "instruction"}:
            raise HTTPException(status_code=422, detail="room file purpose must be artifact or instruction")
        return normalized

    @router.get("/managed/workspaces/{slug}/sessions/{session_id}/files")
    async def managed_workspace_session_files(
        slug: str,
        session_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        files = principal_store.list_room_files(session_id=record.session_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "files": [_sanitize_room_file(item) for item in files],
                **_room_file_quota_payload(files),
            }
        )

    @router.post("/managed/workspaces/{slug}/sessions/{session_id}/files")
    async def managed_upload_workspace_session_file(
        slug: str,
        session_id: str,
        purpose: str = Form(default="artifact"),
        file: UploadFile = File(...),
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        principal, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        content = await _read_room_file_upload(file)
        existing_files = principal_store.list_room_files(session_id=record.session_id)
        _require_room_file_quota(existing_files, next_size_bytes=len(content))
        created = principal_store.create_room_file(
            session_id=record.session_id,
            workspace_id=workspace.workspace_id,
            filename=file.filename or "room-file",
            purpose=_normalize_room_file_purpose(purpose),
            content_type=file.content_type or "application/octet-stream",
            content=content,
            uploaded_by_type="owner",
            uploaded_by_name=principal.email,
        )
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "file": _sanitize_room_file(created),
            }
        )

    @router.get("/managed/workspaces/{slug}/sessions/{session_id}/files/{file_id}")
    async def managed_download_workspace_session_file(
        slug: str,
        session_id: str,
        file_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> Response:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        file_record = principal_store.get_room_file(file_id=file_id)
        if file_record is None or file_record.session_id != record.session_id or file_record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="room file does not exist")
        return _room_file_download_response(file_record)

    @router.delete("/managed/workspaces/{slug}/sessions/{session_id}/files/{file_id}")
    async def managed_delete_workspace_session_file(
        slug: str,
        session_id: str,
        file_id: str,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        _, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        file_record = principal_store.get_room_file(file_id=file_id)
        if file_record is None or file_record.session_id != record.session_id or file_record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="room file does not exist")
        deleted = principal_store.delete_room_file(file_id=file_id)
        return JSONResponse(
            {
                "status": "deleted" if deleted else "not_found",
                "workspace": _sanitize_workspace(workspace),
                "workspace_session": _sanitize_workspace_session(record, include_owner_member_token=True),
                "file_id": file_id,
            }
        )

    def _new_web_operator_agent_name() -> str:
        return f"web-operator-{uuid4().hex[:12]}"

    async def _active_session_detail_or_404(session_id: str) -> dict[str, object]:
        try:
            detail = await runtime.coordination.session_detail(
                session_id=session_id,
                include_join_code=True,
            )
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="managed workspace session is not active") from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="managed workspace session is not active") from exc
        if not isinstance(detail, dict):
            raise HTTPException(status_code=404, detail="managed workspace session is not active")
        return detail

    def _session_has_member(session_detail: dict[str, object], agent_name: str) -> bool:
        members = session_detail.get("members")
        if not isinstance(members, list):
            return False
        for member in members:
            if isinstance(member, dict) and member.get("agent_name") == agent_name:
                return True
        return False

    async def _join_web_operator(
        *,
        session_detail: dict[str, object],
        agent_name: str,
    ) -> str:
        join_code = session_detail.get("join_code")
        if not isinstance(join_code, str) or not join_code.strip():
            raise HTTPException(status_code=409, detail="join_code is not available for this session")
        try:
            joined = await runtime.coordination.join_session(
                join_code=join_code,
                agent_name=agent_name,
                capabilities=["web_operator"],
                delivery_mode="attached",
                provider="managed-web",
            )
        except SessionAccessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        member_token = joined.get("member_token") if isinstance(joined, dict) else None
        if not isinstance(member_token, str) or not member_token:
            raise HTTPException(status_code=500, detail="web operator member token was not issued")
        return member_token

    @router.post("/managed/workspaces/{slug}/sessions/{session_id}/operator/send")
    async def managed_workspace_session_operator_send(
        slug: str,
        session_id: str,
        payload: SendRoomOperatorMessageRequest,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        principal, workspace, record = _require_workspace_session_record(
            slug=slug,
            session_id=session_id,
            acp_managed_session=acp_managed_session,
        )
        destination = payload.to.strip()
        body = payload.payload.strip()
        if not destination:
            raise HTTPException(status_code=422, detail="to is required")
        if not body:
            raise HTTPException(status_code=422, detail="payload is required")

        session_detail = await _active_session_detail_or_404(record.session_id)
        operator = principal_store.get_room_operator(
            session_id=record.session_id,
            principal_email=principal.email,
        )
        created = False
        if operator is None:
            operator_agent_name = _new_web_operator_agent_name()
            member_token = await _join_web_operator(
                session_detail=session_detail,
                agent_name=operator_agent_name,
            )
            operator = principal_store.upsert_room_operator(
                session_id=record.session_id,
                workspace_id=workspace.workspace_id,
                principal_email=principal.email,
                operator_agent_name=operator_agent_name,
                member_token=member_token,
            )
            created = True
        elif not _session_has_member(session_detail, operator.operator_agent_name):
            member_token = await _join_web_operator(
                session_detail=session_detail,
                agent_name=operator.operator_agent_name,
            )
            operator = principal_store.upsert_room_operator(
                session_id=record.session_id,
                workspace_id=workspace.workspace_id,
                principal_email=principal.email,
                operator_agent_name=operator.operator_agent_name,
                member_token=member_token,
            )

        message_id = str(uuid4())
        envelope = {
            "type": "MSG",
            "id": message_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "from": operator.operator_agent_name,
            "to": destination,
            "action": payload.action.upper(),
            "payload": body,
            "thread_id": None,
            "in_reply_to": None,
            "session_id": record.session_id,
        }
        try:
            sent = await runtime.coordination.send_message(
                session_id=record.session_id,
                agent_name=operator.operator_agent_name,
                member_token=operator.member_token,
                payload=envelope,
            )
        except SessionAccessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="managed workspace session is not active") from exc

        return JSONResponse(
            {
                "status": "sent",
                "workspace": _sanitize_workspace(workspace),
                "session_id": record.session_id,
                "operator": {
                    "operator_id": operator.operator_id,
                    "agent_name": operator.operator_agent_name,
                    "created": created,
                },
                "message": {
                    "id": message_id,
                    "to": destination,
                    "action": payload.action.upper(),
                },
                "send_result": sent,
            }
        )

    return router
