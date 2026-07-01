from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException

from acp_managed.auth.session import ManagedSession, SessionTokenManager
from acp_managed.auth.sqlite_store import (
    ManagedWorkspace,
    ManagedWorkspaceMembership,
    ManagedWorkspaceSessionRecord,
    SqliteManagedPrincipalStore,
)
from acp_managed.auth.whitelist import ManagedPrincipal


@dataclass
class ManagedAccessService:
    principal_store: SqliteManagedPrincipalStore
    session_manager: SessionTokenManager

    def current_session_from_cookie(self, acp_managed_session: str | None) -> ManagedSession:
        if not isinstance(acp_managed_session, str) or not acp_managed_session.strip():
            raise HTTPException(status_code=401, detail="missing or invalid managed session")
        token_hash = self.session_manager.hash_token(acp_managed_session)
        self.principal_store.cleanup_expired_browser_sessions(now_ts=int(time.time()))
        record = self.principal_store.get_browser_session_by_token_hash(token_hash=token_hash)
        if record is None:
            raise HTTPException(status_code=401, detail="missing or invalid managed session")
        return ManagedSession(
            session_id=record.session_id,
            email=record.email,
            role=record.role,
            issued_at=record.issued_at,
            expires_at=record.expires_at,
        )

    def current_principal_from_cookie(self, acp_managed_session: str | None) -> ManagedPrincipal:
        session = self.current_session_from_cookie(acp_managed_session)
        principal = self.principal_store.get(session.email)
        if principal is None or principal.status != "active":
            raise HTTPException(status_code=401, detail="unknown managed principal")
        return principal

    def require_workspace_access(
        self,
        *,
        slug: str,
        acp_managed_session: str | None,
    ) -> tuple[ManagedPrincipal, ManagedWorkspace, ManagedWorkspaceMembership | None]:
        principal = self.current_principal_from_cookie(acp_managed_session)
        workspace = self.principal_store.get_workspace_by_slug(slug)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        if workspace.status != "active":
            raise HTTPException(status_code=403, detail="managed workspace is disabled")
        membership = self.principal_store.get_membership(workspace_id=workspace.workspace_id, email=principal.email)
        if membership is None or membership.status != "active":
            raise HTTPException(status_code=403, detail="workspace access required")
        return principal, workspace, membership

    def require_workspace_admin_access(
        self,
        *,
        slug: str,
        acp_managed_session: str | None,
    ) -> tuple[ManagedPrincipal, ManagedWorkspace, ManagedWorkspaceMembership | None]:
        principal, workspace, membership = self.require_workspace_access(
            slug=slug,
            acp_managed_session=acp_managed_session,
        )
        if membership is None or membership.role != "workspace_admin":
            raise HTTPException(status_code=403, detail="workspace_admin role required")
        return principal, workspace, membership

    def require_workspace_session_record(
        self,
        *,
        slug: str,
        session_id: str,
    ) -> tuple[ManagedWorkspace, ManagedWorkspaceSessionRecord]:
        workspace = self.principal_store.get_workspace_by_slug(slug)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        record = self.principal_store.get_workspace_session(session_id=session_id)
        if record is None or record.workspace_id != workspace.workspace_id:
            raise HTTPException(status_code=404, detail="managed workspace session does not exist")
        return workspace, record
