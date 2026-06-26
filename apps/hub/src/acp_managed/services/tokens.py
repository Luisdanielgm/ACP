from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException, Request

from acp_managed.auth.session import AgentTokenManager
from acp_managed.auth.sqlite_store import ManagedAgentTokenRecord, ManagedWorkspace, SqliteManagedPrincipalStore

WorkspaceLabelFactory = Callable[..., str]


@dataclass
class ManagedWorkspaceTokenService:
    principal_store: SqliteManagedPrincipalStore
    agent_token_manager: AgentTokenManager
    default_label_factory: WorkspaceLabelFactory

    def current_agent_token(
        self,
        *,
        request: Request,
        slug: str | None = None,
        requested_agent_name: str | None = None,
    ) -> tuple[ManagedAgentTokenRecord, ManagedWorkspace]:
        raw_token = request.headers.get("X-ACP-Agent-Token")
        if not isinstance(raw_token, str) or not raw_token.strip():
            authorization = request.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                raw_token = authorization[len("Bearer ") :].strip()
        if not isinstance(raw_token, str) or not raw_token.strip():
            raise HTTPException(status_code=401, detail="managed agent token is required")
        token_record = self.principal_store.get_agent_token_by_hash(
            token_hash=self.agent_token_manager.hash_token(raw_token.strip())
        )
        if token_record is None or token_record.status != "active":
            raise HTTPException(status_code=401, detail="managed agent token is invalid")
        workspace = self.principal_store.get_workspace_by_id(token_record.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        if isinstance(slug, str) and slug.strip():
            requested_workspace = self.principal_store.get_workspace_by_slug(slug.strip())
            if requested_workspace is None or requested_workspace.workspace_id != token_record.workspace_id:
                raise HTTPException(status_code=403, detail="managed agent token does not grant access to this workspace")
        if workspace.status != "active":
            raise HTTPException(status_code=403, detail="managed workspace is disabled")
        if requested_agent_name is not None and token_record.agent_name not in {None, "", requested_agent_name.strip()}:
            raise HTTPException(status_code=403, detail="managed agent token is bound to a different agent_name")
        self.principal_store.touch_agent_token(token_id=token_record.token_id, last_used_at=int(time.time()))
        return token_record, workspace

    def issue_workspace_agent_token(
        self,
        *,
        workspace: ManagedWorkspace,
        created_by_email: str,
        agent_name: str | None,
        label: str | None = None,
    ) -> tuple[ManagedAgentTokenRecord, str]:
        normalized_agent_name = agent_name.strip() if isinstance(agent_name, str) and agent_name.strip() else None
        normalized_label = label.strip() if isinstance(label, str) and label.strip() else self.default_label_factory(
            workspace=workspace,
            agent_name=normalized_agent_name,
        )
        raw_token = self.agent_token_manager.issue_token()
        record = ManagedAgentTokenRecord(
            token_id=str(uuid4()),
            workspace_id=workspace.workspace_id,
            label=normalized_label,
            agent_name=normalized_agent_name,
            token_hash=self.agent_token_manager.hash_token(raw_token),
            token_hint=raw_token[-6:],
            status="active",
            created_by_email=created_by_email,
            created_at=int(time.time()),
            last_used_at=None,
        )
        self.principal_store.create_agent_token(record)
        return record, raw_token

    def revoke_active_workspace_token(self, *, workspace: ManagedWorkspace) -> ManagedAgentTokenRecord:
        active_token = self.principal_store.get_active_agent_token_for_workspace(workspace_id=workspace.workspace_id)
        if active_token is None:
            raise HTTPException(status_code=404, detail="workspace token does not exist")
        return self.principal_store.revoke_agent_token(token_id=active_token.token_id)
