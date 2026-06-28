"""Agent (Bearer-token) routes — de-tangle slice (A-DETANGLE-07).

The /managed/agent/* surface authenticated by a workspace agent token (Bearer),
via current_agent_token: bootstrap, plus workspace-session create/list/detail/
replay/join/close (each with an auto-resolve and a slug-scoped twin).

SECURITY INVARIANT (preserved verbatim): agent/Bearer responses must NEVER
include the owner_member_token. Every _sanitize_workspace_session(...) call here
omits include_owner_member_token (defaults to False) — only the browser
workspace-admin router exposes it. Do not add the flag to this module.

All dependencies come from the ManagedRouterDeps seam.
"""

from __future__ import annotations

import re
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from acp.hub.coordination_service import SessionAccessError

from acp_managed.contracts import (
    CreateAgentRoomWallPostRequest,
    CloseWorkspaceSessionRequest,
    CreateWorkspaceSessionRequest,
    JoinWorkspaceSessionRequest,
)
from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing._helpers import (
    _filter_managed_replay_history,
    _managed_agent_bootstrap_payload,
    _managed_session_aliases,
    _sanitize_agent_token,
    _sanitize_room_file,
    _sanitize_room_wall_post,
    _sanitize_workspace,
    _sanitize_workspace_session,
)


def build_agent_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    principal_store = deps.principal_store
    runtime = deps.runtime
    _audit = deps.audit
    current_agent_token = deps.token_service.current_agent_token
    create_workspace_session_entry = deps.workspace_session_service.create_workspace_session_entry
    close_workspace_session_entry = deps.workspace_session_service.close_workspace_session_entry

    @router.get("/managed/agent/bootstrap")
    async def managed_agent_bootstrap(request: Request) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request)
        return JSONResponse(
            {
                "status": "ok",
                **_managed_agent_bootstrap_payload(
                    request=request,
                    workspace=workspace,
                    token_record=token_record,
                ),
            }
        )

    async def _managed_agent_create_workspace_session_response(
        *,
        request: Request,
        payload: CreateWorkspaceSessionRequest,
        slug: str | None = None,
    ) -> JSONResponse:
        requested_agent_name = payload.agent_name.strip()
        if not requested_agent_name:
            raise HTTPException(status_code=422, detail="agent_name is required")
        token_record, workspace = current_agent_token(
            request=request,
            slug=slug,
            requested_agent_name=requested_agent_name,
        )
        try:
            record, result = await create_workspace_session_entry(
                workspace=workspace,
                created_by_email=token_record.created_by_email,
                owner_agent_name=requested_agent_name,
                title=payload.title.strip() if isinstance(payload.title, str) and payload.title.strip() else None,
                project=payload.project.strip() if isinstance(payload.project, str) and payload.project.strip() else None,
                capabilities=payload.capabilities,
                # Workspace-scoped tokens should behave like the workspace UI:
                # common names such as codex-chief must not become a dead end
                # just because another active room already owns that global
                # agent name. Agent-bound tokens stay strict because their
                # token claim is for one exact agent identity.
                resolve_name_conflicts=token_record.agent_name in {None, ""},
            )
        except SessionAccessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "acp_session": result,
                **_managed_session_aliases(record=record, acp_session=result),
            }
        )

    async def _managed_agent_list_workspace_sessions_response(
        *,
        request: Request,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
        records = principal_store.list_workspace_sessions(workspace_id=workspace.workspace_id)
        sessions = [_sanitize_workspace_session(item) for item in records]
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "sessions": sessions,
                "workspace_sessions": sessions,
                "count": len(records),
            }
        )

    async def _managed_agent_workspace_session_detail_response(
        *,
        request: Request,
        session_id: str,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
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
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "acp_session": session_detail,
                **_managed_session_aliases(
                    record=record,
                    acp_session=session_detail if isinstance(session_detail, dict) else None,
                ),
            }
        )

    async def _managed_agent_workspace_session_replay_response(
        *,
        request: Request,
        session_id: str,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")

        actor = request.query_params.get("actor")
        if actor is not None:
            actor = actor.strip()
            if not actor or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", actor) is None:
                raise HTTPException(status_code=400, detail="actor must be a valid agent name")

        action = request.query_params.get("action")
        if action is not None:
            action = action.strip().upper()
            if action not in {"TASK", "REPLY", "INFO"}:
                raise HTTPException(status_code=400, detail="action must be TASK, REPLY, or INFO")

        event_type = request.query_params.get("event_type")
        if event_type is not None:
            event_type = event_type.strip().lower()
            if not event_type or re.fullmatch(r"[a-z_]{1,64}", event_type) is None:
                raise HTTPException(status_code=400, detail="event_type must be a valid event name")

        order = request.query_params.get("order", "desc").strip().lower()
        if order not in {"asc", "desc"}:
            raise HTTPException(status_code=400, detail="order must be asc or desc")
        try:
            limit = int(request.query_params.get("limit", "50"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="limit must be an integer") from exc
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit must be > 0")
        limit = min(limit, 200)

        try:
            session_detail = await runtime.coordination.session_detail(
                session_id=session_id,
                include_join_code=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="managed workspace session is not active") from exc
        history = session_detail.get("history") if isinstance(session_detail, dict) else []
        events = _filter_managed_replay_history(
            session_id=session_id,
            history=history if isinstance(history, list) else [],
            actor=actor,
            action=action,
            event_type=event_type,
            order=order,
            limit=limit,
        )
        return JSONResponse(
            {
                "events": events,
                "next_cursor": None,
                "order": order,
                "limit": limit,
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
            }
        )

    async def _managed_agent_workspace_session_wall_response(
        *,
        request: Request,
        session_id: str,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        posts = principal_store.list_room_wall_posts(session_id=record.session_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "posts": [_sanitize_room_wall_post(item) for item in posts],
                "count": len(posts),
            }
        )

    def _room_file_download_response(file_record) -> Response:
        quoted_name = urllib.parse.quote(file_record.filename, safe="")
        return Response(
            content=file_record.content,
            media_type=file_record.content_type,
            headers={"content-disposition": f"attachment; filename*=UTF-8''{quoted_name}"},
        )

    async def _managed_agent_workspace_session_files_response(
        *,
        request: Request,
        session_id: str,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        files = principal_store.list_room_files(session_id=record.session_id)
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "files": [_sanitize_room_file(item) for item in files],
                "count": len(files),
                "total_bytes": sum(item.size_bytes for item in files),
            }
        )

    async def _managed_agent_workspace_session_file_download_response(
        *,
        request: Request,
        session_id: str,
        file_id: str,
        slug: str | None = None,
    ) -> Response:
        _, workspace = current_agent_token(request=request, slug=slug)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        file_record = principal_store.get_room_file(file_id=file_id)
        if (
            file_record is None
            or file_record.session_id != record.session_id
            or file_record.workspace_id != workspace.workspace_id
        ):
            raise HTTPException(status_code=404, detail="room file does not exist")
        return _room_file_download_response(file_record)

    async def _managed_agent_create_workspace_session_wall_post_response(
        *,
        request: Request,
        session_id: str,
        payload: CreateAgentRoomWallPostRequest,
        slug: str | None = None,
    ) -> JSONResponse:
        requested_agent_name = payload.agent_name.strip()
        if not requested_agent_name:
            raise HTTPException(status_code=422, detail="agent_name is required")
        token_record, workspace = current_agent_token(
            request=request,
            slug=slug,
            requested_agent_name=requested_agent_name,
        )
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        post = principal_store.create_room_wall_post(
            session_id=record.session_id,
            workspace_id=workspace.workspace_id,
            author_type="agent",
            author_name=requested_agent_name,
            body=payload.body,
            pinned=False,
        )
        return JSONResponse(
            {
                "status": "created",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "post": _sanitize_room_wall_post(post),
            }
        )

    async def _managed_agent_join_workspace_session_response(
        *,
        request: Request,
        session_id: str,
        payload: JoinWorkspaceSessionRequest,
        slug: str | None = None,
    ) -> JSONResponse:
        requested_agent_name = payload.agent_name.strip()
        if not requested_agent_name:
            raise HTTPException(status_code=422, detail="agent_name is required")
        token_record, workspace = current_agent_token(
            request=request,
            slug=slug,
            requested_agent_name=requested_agent_name,
        )
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        try:
            session_detail = await runtime.coordination.session_detail(
                session_id=session_id,
                include_join_code=True,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="managed workspace session is not active") from exc
        session_payload = session_detail if isinstance(session_detail, dict) else None
        join_code = session_payload.get("join_code") if isinstance(session_payload, dict) else None
        if not isinstance(join_code, str) or not join_code.strip():
            raise HTTPException(status_code=409, detail="join_code is not available for this session")
        try:
            joined = await runtime.coordination.join_session(
                join_code=join_code,
                agent_name=requested_agent_name,
                capabilities=payload.capabilities,
            )
        except SessionAccessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(
            {
                "status": "joined",
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                "acp_session": joined,
                **_managed_session_aliases(record=record, acp_session=joined),
            }
        )

    async def _managed_agent_close_workspace_session_response(
        *,
        request: Request,
        session_id: str,
        payload: CloseWorkspaceSessionRequest | None = None,
        slug: str | None = None,
    ) -> JSONResponse:
        token_record, workspace = current_agent_token(request=request, slug=slug)
        record = principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        if token_record.agent_name not in {None, "", record.owner_agent_name}:
            raise HTTPException(status_code=403, detail="managed agent token can only close sessions owned by that agent_name")
        actor_name = token_record.agent_name.strip() if isinstance(token_record.agent_name, str) and token_record.agent_name.strip() else "workspace-token"
        result = await close_workspace_session_entry(
            record=record,
            actor=f"managed-agent:{actor_name}",
            detail=payload.detail.strip() if payload is not None and isinstance(payload.detail, str) and payload.detail.strip() else None,
        )
        _audit(
            request,
            "managed.agent_session_closed",
            actor_email=token_record.created_by_email,
            target_type="workspace_session",
            target_id=record.session_id,
            metadata={
                "workspace_id": workspace.workspace_id,
                "workspace_slug": workspace.slug,
                "token_id": token_record.token_id,
                "token_scope": "agent" if isinstance(token_record.agent_name, str) and token_record.agent_name.strip() else "workspace",
                "session_closed": result.get("session_closed"),
                "workspace_session_deleted": result.get("workspace_session_deleted"),
                "close_error": result.get("close_error"),
            },
        )
        return JSONResponse(
            {
                "workspace": _sanitize_workspace(workspace),
                "agent_token": _sanitize_agent_token(token_record),
                "workspace_session": _sanitize_workspace_session(record),
                **result,
            }
        )

    @router.post("/managed/agent/sessions")
    async def managed_agent_create_workspace_session_auto(
        payload: CreateWorkspaceSessionRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_create_workspace_session_response(request=request, payload=payload)

    @router.post("/managed/agent/workspaces/{slug}/sessions")
    async def managed_agent_create_workspace_session(
        slug: str,
        payload: CreateWorkspaceSessionRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_create_workspace_session_response(request=request, payload=payload, slug=slug)

    @router.get("/managed/agent/sessions")
    async def managed_agent_list_workspace_sessions_auto(
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_list_workspace_sessions_response(request=request)

    @router.get("/managed/agent/workspaces/{slug}/sessions")
    async def managed_agent_list_workspace_sessions(
        slug: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_list_workspace_sessions_response(request=request, slug=slug)

    @router.get("/managed/agent/sessions/{session_id}")
    async def managed_agent_workspace_session_detail_auto(
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_detail_response(request=request, session_id=session_id)

    @router.get("/managed/agent/workspaces/{slug}/sessions/{session_id}")
    async def managed_agent_workspace_session_detail(
        slug: str,
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_detail_response(request=request, session_id=session_id, slug=slug)

    @router.get("/managed/agent/sessions/{session_id}/replay")
    async def managed_agent_workspace_session_replay_auto(
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_replay_response(request=request, session_id=session_id)

    @router.get("/managed/agent/workspaces/{slug}/sessions/{session_id}/replay")
    async def managed_agent_workspace_session_replay(
        slug: str,
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_replay_response(request=request, session_id=session_id, slug=slug)

    @router.get("/managed/agent/sessions/{session_id}/wall")
    async def managed_agent_workspace_session_wall_auto(
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_wall_response(request=request, session_id=session_id)

    @router.get("/managed/agent/workspaces/{slug}/sessions/{session_id}/wall")
    async def managed_agent_workspace_session_wall(
        slug: str,
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_wall_response(request=request, session_id=session_id, slug=slug)

    @router.post("/managed/agent/sessions/{session_id}/wall")
    async def managed_agent_create_workspace_session_wall_post_auto(
        session_id: str,
        payload: CreateAgentRoomWallPostRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_create_workspace_session_wall_post_response(
            request=request,
            session_id=session_id,
            payload=payload,
        )

    @router.post("/managed/agent/workspaces/{slug}/sessions/{session_id}/wall")
    async def managed_agent_create_workspace_session_wall_post(
        slug: str,
        session_id: str,
        payload: CreateAgentRoomWallPostRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_create_workspace_session_wall_post_response(
            request=request,
            session_id=session_id,
            payload=payload,
            slug=slug,
        )

    @router.get("/managed/agent/sessions/{session_id}/files")
    async def managed_agent_workspace_session_files_auto(
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_files_response(request=request, session_id=session_id)

    @router.get("/managed/agent/workspaces/{slug}/sessions/{session_id}/files")
    async def managed_agent_workspace_session_files(
        slug: str,
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_workspace_session_files_response(request=request, session_id=session_id, slug=slug)

    @router.get("/managed/agent/sessions/{session_id}/files/{file_id}")
    async def managed_agent_workspace_session_file_download_auto(
        session_id: str,
        file_id: str,
        request: Request,
    ) -> Response:
        return await _managed_agent_workspace_session_file_download_response(
            request=request,
            session_id=session_id,
            file_id=file_id,
        )

    @router.get("/managed/agent/workspaces/{slug}/sessions/{session_id}/files/{file_id}")
    async def managed_agent_workspace_session_file_download(
        slug: str,
        session_id: str,
        file_id: str,
        request: Request,
    ) -> Response:
        return await _managed_agent_workspace_session_file_download_response(
            request=request,
            session_id=session_id,
            file_id=file_id,
            slug=slug,
        )

    @router.post("/managed/agent/sessions/{session_id}/join")
    async def managed_agent_join_workspace_session_auto(
        session_id: str,
        payload: JoinWorkspaceSessionRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_join_workspace_session_response(
            request=request,
            session_id=session_id,
            payload=payload,
        )

    @router.post("/managed/agent/workspaces/{slug}/sessions/{session_id}/join")
    async def managed_agent_join_workspace_session(
        slug: str,
        session_id: str,
        payload: JoinWorkspaceSessionRequest,
        request: Request,
    ) -> JSONResponse:
        return await _managed_agent_join_workspace_session_response(
            request=request,
            session_id=session_id,
            payload=payload,
            slug=slug,
        )

    @router.post("/managed/agent/sessions/{session_id}/close")
    async def managed_agent_close_workspace_session_auto(
        session_id: str,
        request: Request,
        payload: CloseWorkspaceSessionRequest | None = None,
    ) -> JSONResponse:
        return await _managed_agent_close_workspace_session_response(
            request=request,
            session_id=session_id,
            payload=payload,
        )

    @router.post("/managed/agent/workspaces/{slug}/sessions/{session_id}/close")
    async def managed_agent_close_workspace_session(
        slug: str,
        session_id: str,
        request: Request,
        payload: CloseWorkspaceSessionRequest | None = None,
    ) -> JSONResponse:
        return await _managed_agent_close_workspace_session_response(
            request=request,
            session_id=session_id,
            payload=payload,
            slug=slug,
        )

    return router
