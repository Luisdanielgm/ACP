from __future__ import annotations

from dataclasses import dataclass

from acp.hub.app import HubRuntime
from acp.hub.coordination_service import SessionAccessError

from acp_managed.auth.sqlite_store import (
    ManagedWorkspace,
    ManagedWorkspaceSessionRecord,
    SqliteManagedPrincipalStore,
)


@dataclass
class ManagedWorkspaceSessionService:
    principal_store: SqliteManagedPrincipalStore
    runtime: HubRuntime

    @staticmethod
    def _agent_name_conflict(exc: SessionAccessError) -> bool:
        return "already attached to another session" in str(exc).lower()

    @staticmethod
    def _workspace_agent_candidates(*, owner_agent_name: str, workspace: ManagedWorkspace) -> list[str]:
        requested = owner_agent_name.strip()
        if not requested:
            return []
        workspace_slug = workspace.slug.strip() or "workspace"
        scoped = f"{requested}--{workspace_slug}"
        candidates = [requested]
        if scoped != requested:
            candidates.append(scoped)
        for index in range(2, 100):
            candidates.append(f"{scoped}-{index}")
        return candidates

    async def create_workspace_session_entry(
        self,
        *,
        workspace: ManagedWorkspace,
        created_by_email: str,
        owner_agent_name: str,
        title: str | None = None,
        project: str | None = None,
        prompt: str | None = None,
        capabilities: list[str] | None = None,
        resolve_name_conflicts: bool = False,
    ) -> tuple[ManagedWorkspaceSessionRecord, dict[str, object]]:
        result: dict[str, object] | None = None
        resolved_agent_name = owner_agent_name.strip()
        last_conflict: SessionAccessError | None = None

        candidates = (
            self._workspace_agent_candidates(owner_agent_name=owner_agent_name, workspace=workspace)
            if resolve_name_conflicts
            else [resolved_agent_name]
        )
        for candidate in candidates:
            try:
                result = await self.runtime.coordination.create_session(
                    owner_agent=candidate,
                    title=title,
                    project=project,
                    capabilities=capabilities,
                )
                resolved_agent_name = candidate
                break
            except SessionAccessError as exc:
                if not resolve_name_conflicts or not self._agent_name_conflict(exc):
                    raise
                last_conflict = exc

        if result is None:
            if last_conflict is not None:
                raise last_conflict
            raise SessionAccessError("agent_name is unavailable for a managed workspace session.")

        session = result["session"]
        record = ManagedWorkspaceSessionRecord(
            session_id=str(result["session_id"]),
            workspace_id=workspace.workspace_id,
            created_by_email=created_by_email,
            owner_agent_name=resolved_agent_name,
            owner_member_token=str(result["member_token"]) if result.get("member_token") is not None else None,
            title=str(session.get("title")) if session.get("title") is not None else None,
            project=str(session.get("project")) if session.get("project") is not None else None,
            created_at=str(session.get("created_at")),
            prompt=prompt.strip() if isinstance(prompt, str) and prompt.strip() else None,
        )
        self.principal_store.create_workspace_session(record)
        return record, result

    async def close_workspace_session_entry(
        self,
        *,
        record: ManagedWorkspaceSessionRecord,
        actor: str,
        detail: str | None = None,
    ) -> dict[str, object]:
        close_result: dict[str, object] | None = None
        close_error: str | None = None
        try:
            close_result = await self.runtime.coordination.admin_close_session(
                session_id=record.session_id,
                actor=actor,
                detail=detail,
            )
        except SessionAccessError as exc:
            # Managed workspace records can outlive the core ACP room after a
            # crash/redeploy/manual close. Cleanup must still remove that stale
            # managed record so agents can recover without dashboard cookies.
            close_error = str(exc)

        deleted = self.principal_store.delete_workspace_session(session_id=record.session_id)
        core_session_closed = bool(close_result.get("session_closed")) if isinstance(close_result, dict) else False
        core_session_already_gone = close_result is None and close_error is not None
        status = "already-gone" if core_session_already_gone and deleted else "closed"
        return {
            "status": status,
            "session_id": record.session_id,
            "session_closed": core_session_closed,
            "core_session_already_gone": core_session_already_gone,
            "workspace_session_deleted": deleted,
            "close_error": None if core_session_already_gone and deleted else close_error,
            "acp_session": close_result,
        }
