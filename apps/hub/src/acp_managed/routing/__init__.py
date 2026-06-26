"""Routing package for the managed overlay (extracted from app.py)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from acp.hub.app import HubRuntime
from acp_managed.auth.session import AgentTokenManager, SessionTokenManager
from acp_managed.auth.sqlite_store import SqliteManagedPrincipalStore
from acp_managed.rate_limit import FailureRateLimiter
from acp_managed.services import (
    ManagedAccessService,
    ManagedWorkspaceInvitationService,
    ManagedWorkspaceSessionService,
    ManagedWorkspaceTokenService,
)


@dataclass(frozen=True)
class ManagedRouterDeps:
    """Dependency bundle handed to managed router factories — the de-tangle seam.

    Built once in create_managed_app() and passed to each build_*_router(deps),
    so route handlers stop being closures over create_managed_app() locals.
    A-DETANGLE-02 only constructs it; routes start consuming it from slice 2a on.
    """

    runtime: HubRuntime
    principal_store: SqliteManagedPrincipalStore
    session_manager: SessionTokenManager
    agent_token_manager: AgentTokenManager
    invitation_ttl_seconds: int
    access_service: ManagedAccessService
    token_service: ManagedWorkspaceTokenService
    invitation_service: ManagedWorkspaceInvitationService
    workspace_session_service: ManagedWorkspaceSessionService
    auth_rate_limiter: FailureRateLimiter
    audit: Callable[..., None]


__all__ = ["ManagedRouterDeps"]
