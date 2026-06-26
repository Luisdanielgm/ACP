from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException, Request

from acp_managed.auth.session import SessionTokenManager
from acp_managed.auth.sqlite_store import (
    ManagedWorkspace,
    ManagedWorkspaceAdminInvitationRecord,
    SqliteManagedPrincipalStore,
)


@dataclass
class ManagedWorkspaceInvitationService:
    principal_store: SqliteManagedPrincipalStore
    session_manager: SessionTokenManager
    ttl_seconds: int
    request_origin_resolver: Callable[[Request], str]

    def issue_workspace_admin_invitation(
        self,
        *,
        request: Request,
        workspace: ManagedWorkspace,
        created_by_email: str,
        email: str,
    ) -> tuple[ManagedWorkspaceAdminInvitationRecord, str, str]:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise HTTPException(status_code=422, detail="email is required")
        now_ts = int(time.time())
        raw_token, _, _ = self.session_manager.issue_token()
        record = ManagedWorkspaceAdminInvitationRecord(
            invitation_id=str(uuid4()),
            workspace_id=workspace.workspace_id,
            email=normalized_email,
            token_hash=self.session_manager.hash_token(raw_token),
            status="pending",
            created_by_email=created_by_email,
            created_at=now_ts,
            expires_at=now_ts + self.ttl_seconds,
            accepted_at=None,
            revoked_at=None,
        )
        self.principal_store.create_workspace_admin_invitation(record)
        invitation_url = (
            f"{self.request_origin_resolver(request)}/managed/invitations/"
            f"{urllib.parse.quote(raw_token, safe='')}"
        )
        return record, raw_token, invitation_url

    def load_workspace_admin_invitation(self, raw_token: str) -> ManagedWorkspaceAdminInvitationRecord:
        self.principal_store.cleanup_expired_workspace_admin_invitations(now_ts=int(time.time()))
        invitation = self.principal_store.get_workspace_admin_invitation_by_hash(
            token_hash=self.session_manager.hash_token(raw_token.strip())
        )
        if invitation is None:
            raise HTTPException(status_code=404, detail="workspace admin invitation does not exist")
        if invitation.status != "pending":
            raise HTTPException(status_code=409, detail=f"workspace admin invitation is {invitation.status}")
        if invitation.expires_at <= int(time.time()):
            self.principal_store.update_workspace_admin_invitation_status(
                invitation_id=invitation.invitation_id,
                status="expired",
            )
            raise HTTPException(status_code=410, detail="workspace admin invitation expired")
        return invitation
