"""Instance-admin routes — de-tangle slice (A-DETANGLE-05).

The /managed/admin/* surface guarded by require_instance_admin: workspace
listing, audit log, workspace create/disable/update/delete, and workspace-admin
invitations. All dependencies come from the ManagedRouterDeps seam.

The agent-token and preset routes that live under /managed/admin/workspaces/{slug}
are guarded by require_workspace_admin_access instead, so they belong to the
workspace-admin slice (A-DETANGLE-06), not here.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse

from acp_managed.auth.sqlite_store import ManagedWorkspace, ManagedWorkspaceMembership
from acp_managed.contracts import (
    CreateWorkspaceAdminInvitationRequest,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
)
from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing._helpers import (
    _allocate_workspace_slug,
    _sanitize_membership,
    _sanitize_workspace,
    _sanitize_workspace_admin_invitation,
)


def build_instance_admin_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    principal_store = deps.principal_store
    _audit = deps.audit
    require_instance_admin = deps.access_service.require_instance_admin
    issue_workspace_admin_invitation = deps.invitation_service.issue_workspace_admin_invitation

    @router.get("/managed/admin/workspaces")
    async def managed_list_workspaces(acp_managed_session: str | None = Cookie(default=None)) -> JSONResponse:
        require_instance_admin(acp_managed_session)
        workspaces = principal_store.list_workspaces()
        payload = []
        for workspace in workspaces:
            admin_membership = principal_store.get_workspace_admin_membership(workspace_id=workspace.workspace_id)
            payload.append(
                {
                    "workspace": _sanitize_workspace(workspace),
                    "workspace_admin": _sanitize_membership(admin_membership) if admin_membership is not None else None,
                    "invitations": [
                        _sanitize_workspace_admin_invitation(item)
                        for item in principal_store.list_workspace_admin_invitations(workspace_id=workspace.workspace_id)
                    ],
                }
            )
        return JSONResponse({"workspaces": payload, "count": len(payload)})

    @router.get("/managed/admin/audit")
    async def managed_audit_log(
        acp_managed_session: str | None = Cookie(default=None),
        limit: int = 100,
        actor_email: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
    ) -> JSONResponse:
        require_instance_admin(acp_managed_session)
        events = principal_store.list_audit_events(
            limit=limit,
            actor_email=actor_email,
            action=action,
            target_type=target_type,
        )
        import json as _json
        items = []
        for event in events:
            metadata = None
            if event.metadata_json:
                try:
                    metadata = _json.loads(event.metadata_json)
                except (ValueError, TypeError):
                    metadata = {"raw": event.metadata_json}
            items.append({
                "audit_id": event.audit_id,
                "created_at": event.created_at,
                "actor_email": event.actor_email,
                "actor_ip": event.actor_ip,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "metadata": metadata,
            })
        return JSONResponse({"events": items, "count": len(items)})

    @router.post("/managed/admin/workspaces")
    async def managed_create_workspace(
        payload: CreateWorkspaceRequest,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal = require_instance_admin(acp_managed_session)
        workspace_name = payload.name.strip()
        if not workspace_name:
            raise HTTPException(status_code=422, detail="workspace name is required")
        workspace_slug = _allocate_workspace_slug(
            principal_store,
            name=workspace_name,
            preferred_slug=payload.slug.strip() if isinstance(payload.slug, str) and payload.slug.strip() else None,
        )
        workspace = ManagedWorkspace(
            workspace_id=str(uuid4()),
            slug=workspace_slug,
            name=workspace_name,
            status=payload.status.strip() or "active",
            created_by=acting_principal.email,
        )
        try:
            principal_store.create_workspace(workspace)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _audit(
            request,
            "managed.workspace_created",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=workspace.workspace_id,
            metadata={"slug": workspace.slug, "name": workspace.name, "status": workspace.status},
        )
        normalized_admin_email = payload.admin_email.strip().lower() if isinstance(payload.admin_email, str) and payload.admin_email.strip() else None
        response_payload: dict[str, object] = {
            "status": "created",
            "workspace": _sanitize_workspace(workspace),
            "workspace_admin": None,
            "invitation": None,
            "invitation_url": None,
            "admin_assignment": "unassigned",
        }
        if normalized_admin_email is not None:
            if normalized_admin_email == acting_principal.email:
                membership = ManagedWorkspaceMembership(
                    workspace_id=workspace.workspace_id,
                    email=acting_principal.email,
                    role="workspace_admin",
                    status="active",
                )
                try:
                    principal_store.add_workspace_membership(membership)
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                response_payload["workspace_admin"] = _sanitize_membership(membership)
                response_payload["admin_assignment"] = "self_assigned"
            else:
                try:
                    invitation, _, invitation_url = issue_workspace_admin_invitation(
                        request=request,
                        workspace=workspace,
                        created_by_email=acting_principal.email,
                        email=normalized_admin_email,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                response_payload["invitation"] = _sanitize_workspace_admin_invitation(invitation)
                response_payload["invitation_url"] = invitation_url
                response_payload["admin_assignment"] = "invited"
        return JSONResponse(response_payload)

    @router.post("/managed/admin/workspaces/{slug}/invite-admin")
    async def managed_invite_workspace_admin(
        slug: str,
        payload: CreateWorkspaceAdminInvitationRequest,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal = require_instance_admin(acp_managed_session)
        workspace = principal_store.get_workspace_by_slug(slug)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        if workspace.status != "active":
            raise HTTPException(status_code=409, detail="managed workspace is disabled")
        existing_admin = principal_store.get_workspace_admin_membership(workspace_id=workspace.workspace_id)
        if existing_admin is not None:
            raise HTTPException(status_code=409, detail="workspace already has an active workspace_admin")
        try:
            invitation, _, invitation_url = issue_workspace_admin_invitation(
                request=request,
                workspace=workspace,
                created_by_email=acting_principal.email,
                email=payload.email,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _audit(
            request,
            "managed.workspace_admin_invited",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=workspace.workspace_id,
            metadata={"slug": workspace.slug, "invitee_email": invitation.email, "invitation_id": invitation.invitation_id},
        )
        return JSONResponse(
            {
                "status": "invited",
                "workspace": _sanitize_workspace(workspace),
                "invitation": _sanitize_workspace_admin_invitation(invitation),
                "invitation_url": invitation_url,
            }
        )

    @router.post("/managed/admin/workspaces/{slug}/disable")
    async def managed_disable_workspace(
        slug: str,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal = require_instance_admin(acp_managed_session)
        try:
            updated = principal_store.update_workspace(slug=slug, status="disabled")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _audit(
            request,
            "managed.workspace_disabled",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=updated.workspace_id,
            metadata={"slug": updated.slug},
        )
        return JSONResponse({"status": "disabled", "workspace": _sanitize_workspace(updated)})

    @router.patch("/managed/admin/workspaces/{slug}")
    async def managed_update_workspace(
        slug: str,
        payload: UpdateWorkspaceRequest,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal = require_instance_admin(acp_managed_session)
        try:
            updated = principal_store.update_workspace(
                slug=slug,
                name=payload.name.strip() if isinstance(payload.name, str) and payload.name.strip() else None,
                status=payload.status.strip() if isinstance(payload.status, str) and payload.status.strip() else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _audit(
            request,
            "managed.workspace_updated",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=updated.workspace_id,
            metadata={"slug": updated.slug, "name": updated.name, "status": updated.status},
        )
        return JSONResponse({"status": "updated", "workspace": _sanitize_workspace(updated)})

    @router.delete("/managed/admin/workspaces/{slug}")
    async def managed_delete_workspace(
        slug: str,
        request: Request,
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        acting_principal = require_instance_admin(acp_managed_session)
        existing = principal_store.get_workspace_by_slug(slug)
        if existing is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        try:
            principal_store.delete_workspace(slug=slug)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _audit(
            request,
            "managed.workspace_deleted",
            actor_email=acting_principal.email,
            target_type="workspace",
            target_id=existing.workspace_id,
            metadata={"slug": existing.slug, "name": existing.name},
        )
        return JSONResponse({"status": "deleted", "workspace_id": existing.workspace_id, "slug": existing.slug})

    return router
