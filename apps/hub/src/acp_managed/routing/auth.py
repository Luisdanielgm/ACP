"""Authentication / session / invitation routes — de-tangle slice (A-DETANGLE-04).

Login (form + JSON), logout (form + JSON), the session/me probes, and the
workspace-admin invitation preview/accept flow. Security-sensitive surface:
preserves the rate-limit (429 + Retry-After), the httponly/samesite/secure
cookie shape, the invitation anti-bypass guard (existing accounts must prove
ownership with their password), and the audit trail.

All dependencies come from the ManagedRouterDeps seam; no closures over
create_managed_app() locals remain here.
"""

from __future__ import annotations

import time
import urllib.parse
from uuid import uuid4

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from acp_managed.auth.passwords import hash_password
from acp_managed.auth.session import ManagedSession
from acp_managed.auth.sqlite_store import (
    ManagedBrowserSessionRecord,
    ManagedWorkspaceMembership,
)
from acp_managed.auth.whitelist import ManagedPrincipal
from acp_managed.contracts import (
    AcceptWorkspaceInvitationRequest,
    LoginRequest,
)
from acp_managed.rate_limit import (
    INVITATION_PER_IP_RULE,
    INVITATION_PER_TOKEN_RULE,
    LOGIN_PER_IP_EMAIL_RULE,
    LOGIN_PER_IP_RULE,
    client_ip_from_request,
)
from acp_managed.routing import ManagedRouterDeps
from acp_managed.routing._helpers import (
    _request_is_secure,
    _sanitize_principal,
    _sanitize_workspace,
    _sanitize_workspace_admin_invitation,
)


def build_auth_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    runtime = deps.runtime
    principal_store = deps.principal_store
    session_manager = deps.session_manager
    auth_rate_limiter = deps.auth_rate_limiter
    _audit = deps.audit
    current_session_from_cookie = deps.access_service.current_session_from_cookie
    current_principal_from_cookie = deps.access_service.current_principal_from_cookie
    load_workspace_admin_invitation = deps.invitation_service.load_workspace_admin_invitation

    def _login_rate_scopes(*, request: Request, email: str | None) -> list[tuple[str, str, object]]:
        ip = client_ip_from_request(request)
        scopes: list[tuple[str, str, object]] = [
            ("login_ip", ip, LOGIN_PER_IP_RULE),
        ]
        normalized_email = (email or "").strip().lower()
        if normalized_email:
            scopes.append(("login_ip_email", f"{ip}|{normalized_email}", LOGIN_PER_IP_EMAIL_RULE))
        return scopes

    def _invitation_rate_scopes(*, request: Request, token: str | None) -> list[tuple[str, str, object]]:
        ip = client_ip_from_request(request)
        scopes: list[tuple[str, str, object]] = [
            ("invitation_ip", ip, INVITATION_PER_IP_RULE),
        ]
        normalized_token = (token or "").strip()
        if normalized_token:
            scopes.append(("invitation_token", normalized_token, INVITATION_PER_TOKEN_RULE))
        return scopes

    def _enforce_rate_limit(scopes: list[tuple[str, str, object]], *, error_detail: str) -> None:
        decision = auth_rate_limiter.check(scopes)
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail=error_detail,
                headers={"Retry-After": str(decision.retry_after)},
            )

    @router.get("/managed/dashboard/auth/session")
    async def managed_session_dashboard_auth_session(
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        try:
            session = current_session_from_cookie(acp_managed_session)
            principal = current_principal_from_cookie(acp_managed_session)
        except HTTPException as exc:
            if exc.status_code == 401:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "anonymous",
                        "authenticated": False,
                        "token_required": getattr(runtime, "required_token", None) is not None,
                    },
                )
            raise
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "authenticated": True,
                "token_required": getattr(runtime, "required_token", None) is not None,
                "managed_session": {
                    "session_id": session.session_id,
                    "email": principal.email,
                    "role": principal.role,
                },
            },
        )

    @router.post("/managed/login")
    async def managed_login_form(request: Request, email: str = Form(...), password: str = Form(...)) -> RedirectResponse:
        scopes = _login_rate_scopes(request=request, email=email)
        decision = auth_rate_limiter.check(scopes)
        if not decision.allowed:
            response = RedirectResponse(url="/managed/login?error=rate_limited", status_code=303)
            response.headers["Retry-After"] = str(decision.retry_after)
            return response
        principal = principal_store.authenticate(email=email, password=password)
        if principal is None:
            auth_rate_limiter.register_failure(scopes)
            return RedirectResponse(url="/managed/login?error=1", status_code=303)
        session_token, issued_at, expires_at = session_manager.issue_token()
        session = ManagedSession(
            session_id=str(uuid4()),
            email=principal.email,
            role=principal.role,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        principal_store.create_browser_session(
            ManagedBrowserSessionRecord(
                session_id=session.session_id,
                email=session.email,
                role=session.role,
                token_hash=session_manager.hash_token(session_token),
                issued_at=session.issued_at,
                expires_at=session.expires_at,
            )
        )
        response = RedirectResponse(url="/managed/dashboard", status_code=303)
        response.set_cookie(
            key="acp_managed_session",
            value=session_token,
            max_age=max(1, session.expires_at - session.issued_at),
            httponly=True,
            samesite="lax",
            secure=_request_is_secure(request),
            path="/",
        )
        return response

    @router.post("/managed/auth/login")
    async def managed_login(payload: LoginRequest, request: Request) -> JSONResponse:
        scopes = _login_rate_scopes(request=request, email=payload.email)
        _enforce_rate_limit(scopes, error_detail="too many login attempts; please retry later")
        principal = principal_store.authenticate(email=payload.email, password=payload.password)
        if principal is None:
            auth_rate_limiter.register_failure(scopes)
            _audit(request, "managed.login_failed", actor_email=payload.email)
            raise HTTPException(status_code=401, detail="invalid credentials")
        _audit(request, "managed.login_succeeded", actor_email=principal.email)
        session_token, issued_at, expires_at = session_manager.issue_token()
        session = ManagedSession(
            session_id=str(uuid4()),
            email=principal.email,
            role=principal.role,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        principal_store.create_browser_session(
            ManagedBrowserSessionRecord(
                session_id=session.session_id,
                email=session.email,
                role=session.role,
                token_hash=session_manager.hash_token(session_token),
                issued_at=session.issued_at,
                expires_at=session.expires_at,
            )
        )
        response = JSONResponse(
            {
                "status": "ok",
                "email": principal.email,
                "role": principal.role,
                "expires_at": session.expires_at,
            }
        )
        response.set_cookie(
            key="acp_managed_session",
            value=session_token,
            max_age=max(1, session.expires_at - session.issued_at),
            httponly=True,
            samesite="lax",
            secure=_request_is_secure(request),
            path="/",
        )
        return response

    @router.get("/managed/invitations/{token}/preview")
    async def managed_workspace_invitation_preview(token: str, request: Request) -> JSONResponse:
        """Non-destructive lookup so the SPA knows whether to show a password field.

        Returns only whether the invitee will need to set a password (i.e. the
        principal does not yet exist). Email and other PII are intentionally
        not echoed because the token alone is the authorization here.
        """
        scopes = _invitation_rate_scopes(request=request, token=token)
        _enforce_rate_limit(scopes, error_detail="too many invitation lookups; please retry later")
        try:
            invitation = load_workspace_admin_invitation(token)
        except HTTPException:
            auth_rate_limiter.register_failure(scopes)
            raise
        workspace = principal_store.get_workspace_by_id(invitation.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        existing_principal = principal_store.get(invitation.email)
        return JSONResponse(
            {
                "status": "pending",
                "requires_password": existing_principal is None,
                "workspace": {"slug": workspace.slug, "name": workspace.name},
            }
        )

    @router.post("/managed/invitations/{token}/accept")
    async def managed_accept_workspace_invitation(
        token: str,
        payload: AcceptWorkspaceInvitationRequest,
        request: Request,
    ) -> JSONResponse:
        scopes = _invitation_rate_scopes(request=request, token=token)
        _enforce_rate_limit(scopes, error_detail="too many invitation attempts; please retry later")
        try:
            invitation = load_workspace_admin_invitation(token)
        except HTTPException:
            auth_rate_limiter.register_failure(scopes)
            raise
        workspace = principal_store.get_workspace_by_id(invitation.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="managed workspace does not exist")
        existing_admin = principal_store.get_workspace_admin_membership(workspace_id=workspace.workspace_id)
        if existing_admin is not None and existing_admin.email != invitation.email:
            raise HTTPException(status_code=409, detail="workspace already has an active workspace_admin")

        principal = principal_store.get(invitation.email)
        if principal is None:
            if not isinstance(payload.password, str) or len(payload.password.strip()) < 8:
                raise HTTPException(status_code=422, detail="password is required to create a new VPS account")
            principal = ManagedPrincipal(
                email=invitation.email,
                password_hash=hash_password(payload.password),
                role="workspace_admin",
                status="active",
            )
            principal_store.create(principal)
        else:
            if principal.status != "active":
                raise HTTPException(status_code=409, detail="invited principal is not active")
            # Existing account: accepting an invitation must prove ownership of the
            # account with its password, otherwise a leaked invitation link would
            # mint a full session for that account (auth bypass).
            if (
                principal_store.authenticate(
                    email=invitation.email,
                    password=payload.password if isinstance(payload.password, str) else "",
                )
                is None
            ):
                raise HTTPException(status_code=401, detail="incorrect password for the invited account")
            if principal.role not in {"instance_admin", "workspace_admin"}:
                principal = principal_store.update_role_status(email=principal.email, role="workspace_admin")

        principal_store.add_workspace_membership(
            ManagedWorkspaceMembership(
                workspace_id=workspace.workspace_id,
                email=invitation.email,
                role="workspace_admin",
                status="active",
            )
        )
        accepted = principal_store.update_workspace_admin_invitation_status(
            invitation_id=invitation.invitation_id,
            status="accepted",
            accepted_at=int(time.time()),
        )
        _audit(
            request,
            "managed.workspace_admin_invitation_accepted",
            actor_email=invitation.email,
            target_type="workspace",
            target_id=workspace.workspace_id,
            metadata={"slug": workspace.slug, "invitation_id": invitation.invitation_id},
        )
        session_token, issued_at, expires_at = session_manager.issue_token()
        session = ManagedSession(
            session_id=str(uuid4()),
            email=principal.email,
            role=principal.role,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        principal_store.create_browser_session(
            ManagedBrowserSessionRecord(
                session_id=session.session_id,
                email=session.email,
                role=session.role,
                token_hash=session_manager.hash_token(session_token),
                issued_at=session.issued_at,
                expires_at=session.expires_at,
            )
        )
        response = JSONResponse(
            {
                "status": "accepted",
                "workspace": _sanitize_workspace(workspace),
                "invitation": _sanitize_workspace_admin_invitation(accepted),
                "principal": _sanitize_principal(principal),
                "redirect_url": f"/managed/ui/workspaces/{urllib.parse.quote(workspace.slug, safe='')}?flash=invitation-accepted",
            }
        )
        response.set_cookie(
            key="acp_managed_session",
            value=session_token,
            max_age=max(1, session.expires_at - session.issued_at),
            httponly=True,
            samesite="lax",
            secure=_request_is_secure(request),
            path="/",
        )
        return response

    @router.post("/managed/invitations/{token}")
    async def managed_accept_workspace_invitation_form(
        token: str,
        request: Request,
        password: str = Form(default=""),
    ) -> RedirectResponse:
        response = await managed_accept_workspace_invitation(
            token=token,
            payload=AcceptWorkspaceInvitationRequest(password=password or None),
            request=request,
        )
        redirect_url = bytes(response.body).decode("utf-8")
        import json as _json

        payload = _json.loads(redirect_url)
        form_response = RedirectResponse(url=payload["redirect_url"], status_code=303)
        for header_name, header_value in response.headers.items():
            if header_name.lower() == "set-cookie":
                form_response.headers.append("set-cookie", header_value)
        return form_response

    @router.get("/managed/auth/me")
    async def managed_me(acp_managed_session: str | None = Cookie(default=None)) -> JSONResponse:
        try:
            session = current_session_from_cookie(acp_managed_session)
            principal = current_principal_from_cookie(acp_managed_session)
        except HTTPException as exc:
            if exc.status_code == 401:
                return JSONResponse(
                    {
                        "authenticated": False,
                        "status": "anonymous",
                    }
                )
            raise
        return JSONResponse(
            {
                "authenticated": True,
                "email": principal.email,
                "role": principal.role,
                "status": principal.status,
                "expires_at": session.expires_at,
            }
        )

    @router.post("/managed/auth/logout")
    async def managed_logout(acp_managed_session: str | None = Cookie(default=None)) -> JSONResponse:
        if isinstance(acp_managed_session, str) and acp_managed_session.strip():
            principal_store.delete_browser_session_by_token_hash(
                token_hash=session_manager.hash_token(acp_managed_session)
            )
        response = JSONResponse({"status": "ok"})
        response.delete_cookie(key="acp_managed_session", path="/")
        return response

    @router.get("/managed/logout")
    @router.post("/managed/logout")
    async def managed_logout_form(acp_managed_session: str | None = Cookie(default=None)) -> RedirectResponse:
        if isinstance(acp_managed_session, str) and acp_managed_session.strip():
            principal_store.delete_browser_session_by_token_hash(
                token_hash=session_manager.hash_token(acp_managed_session)
            )
        response = RedirectResponse(url="/managed/login", status_code=303)
        response.delete_cookie(key="acp_managed_session", path="/")
        return response

    return router
