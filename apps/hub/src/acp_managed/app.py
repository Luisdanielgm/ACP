"""Managed workspace layer mounted on top of the ACP core."""

from __future__ import annotations

from fastapi import FastAPI, Request

from acp.hub.app import create_app, create_runtime_from_env

from acp_managed.auth.session import AgentTokenManager, SessionTokenManager
from acp_managed.ui.spa import _register_managed_vue_spa
from acp_managed.config import (
    managed_agent_token_secret as _managed_agent_token_secret,
    managed_invitation_ttl_seconds as _managed_invitation_ttl_seconds,
    managed_principal_store as _managed_principal_store,
    managed_session_secret as _managed_session_secret,
    managed_session_ttl_seconds as _managed_session_ttl_seconds,
    public_web_enabled as _public_web_enabled,
)
from acp_managed.rate_limit import (
    FailureRateLimiter,
    client_ip_from_request,
)
from acp_managed.services import (
    ManagedAccessService,
    ManagedWorkspaceInvitationService,
    ManagedWorkspaceSessionService,
    ManagedWorkspaceTokenService,
)




from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing.agent import build_agent_router
from acp_managed.routing.auth import build_auth_router
from acp_managed.routing.downloads import build_downloads_router
from acp_managed.routing.instance_admin import build_instance_admin_router
from acp_managed.routing.public_pages import build_public_pages_router
from acp_managed.routing.workspace_admin import build_workspace_admin_router
from acp_managed.routing._helpers import (
    _default_agent_token_label,
    _request_origin,
)


def create_managed_app() -> FastAPI:
    runtime = create_runtime_from_env()
    runtime.public_web_enabled = _public_web_enabled()
    runtime.legacy_dashboard_enabled = False
    app = create_app(runtime=runtime)
    principal_store = _managed_principal_store()
    session_manager = SessionTokenManager(
        secret=_managed_session_secret(),
        ttl_seconds=_managed_session_ttl_seconds(),
    )
    agent_token_manager = AgentTokenManager(secret=_managed_agent_token_secret())
    invitation_ttl_seconds = _managed_invitation_ttl_seconds()
    app.state.managed_principal_store = principal_store
    app.state.managed_session_manager = session_manager
    app.state.managed_agent_token_manager = agent_token_manager
    app.state.managed_runtime = runtime
    access_service = ManagedAccessService(
        principal_store=principal_store,
        session_manager=session_manager,
    )
    token_service = ManagedWorkspaceTokenService(
        principal_store=principal_store,
        agent_token_manager=agent_token_manager,
        default_label_factory=_default_agent_token_label,
    )
    invitation_service = ManagedWorkspaceInvitationService(
        principal_store=principal_store,
        session_manager=session_manager,
        ttl_seconds=invitation_ttl_seconds,
        request_origin_resolver=_request_origin,
    )
    workspace_session_service = ManagedWorkspaceSessionService(
        principal_store=principal_store,
        runtime=runtime,
    )
    auth_rate_limiter = FailureRateLimiter()

    def _audit(
        request: Request,
        action: str,
        *,
        actor_email: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        try:
            principal_store.append_audit_event(
                action=action,
                actor_email=actor_email,
                actor_ip=client_ip_from_request(request),
                target_type=target_type,
                target_id=target_id,
                metadata=metadata,
            )
        except Exception:
            # Audit logging must never break the request. Persistence errors
            # are intentionally swallowed; observability comes from elsewhere.
            pass
    app.state.managed_access_service = access_service
    app.state.managed_workspace_token_service = token_service
    app.state.managed_workspace_invitation_service = invitation_service
    app.state.managed_workspace_session_service = workspace_session_service
    app.state.managed_auth_rate_limiter = auth_rate_limiter

    # The de-tangle seam: one dependency bundle every router factory consumes.
    # create_managed_app() is now thin composition — all routes live in
    # acp_managed.routing.* and are mounted via include_router below.
    deps = ManagedRouterDeps(
        runtime=runtime,
        principal_store=principal_store,
        session_manager=session_manager,
        agent_token_manager=agent_token_manager,
        invitation_ttl_seconds=invitation_ttl_seconds,
        access_service=access_service,
        token_service=token_service,
        invitation_service=invitation_service,
        workspace_session_service=workspace_session_service,
        auth_rate_limiter=auth_rate_limiter,
        audit=_audit,
    )
    app.state.managed_router_deps = deps
    app.include_router(build_public_pages_router(deps))
    app.include_router(build_downloads_router(deps))

    current_principal_from_cookie = access_service.current_principal_from_cookie

    def authorize_managed_session_dashboard_access(*, session_id: str, acp_managed_session: str | None) -> bool:
        if not isinstance(session_id, str) or not session_id.strip():
            return False
        session_record = principal_store.get_workspace_session(session_id=session_id.strip())
        if session_record is None:
            return False
        principal = current_principal_from_cookie(acp_managed_session)
        if principal.role == "instance_admin":
            return True
        membership = principal_store.get_membership(
            workspace_id=session_record.workspace_id,
            email=principal.email,
        )
        return membership is not None and membership.status == "active" and membership.role == "workspace_admin"

    runtime.managed_session_authorizer = authorize_managed_session_dashboard_access

    app.include_router(build_auth_router(deps))
    app.include_router(build_instance_admin_router(deps))
    app.include_router(build_workspace_admin_router(deps))
    app.include_router(build_agent_router(deps))

    # Note: legacy /managed/admin/users/* endpoints were removed. Direct managed
    # user administration is replaced by the workspace-admin invitation flow.
    # FastAPI returns 404 for unknown routes, which is correct here.

    _register_managed_vue_spa(app)

    return app


app = create_managed_app()
