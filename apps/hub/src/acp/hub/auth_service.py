"""Shared authentication adapter for HTTP and WebSocket ingress paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

from acp.protocol.errors import AUTH_FORBIDDEN, AUTH_INVALID, AUTH_REQUIRED, INVALID_FIELD, ProtocolValidationError, build_error


ScopeName = Literal["connect", "send", "observe", "replay"]


@dataclass(frozen=True)
class ScopeDecision:
    scope: ScopeName
    principal: str | None
    surface: str
    decision: Literal["allow", "would_deny", "deny"]
    reason_code: str


class ScopeProvider(Protocol):
    def get_scopes_for_principal(self, principal_name: str) -> set[str] | None:
        ...

    def get_acl_decision(self, *, sender: str, recipient: str, action: str) -> Literal["allow", "deny"] | None:
        ...


class NullScopeProvider:
    def get_scopes_for_principal(self, principal_name: str) -> set[str] | None:
        return None

    def get_acl_decision(self, *, sender: str, recipient: str, action: str) -> Literal["allow", "deny"] | None:
        return None


def extract_http_token(authorization: str | None, x_acp_token: str | None) -> str | None:
    if x_acp_token is not None:
        token = x_acp_token.strip()
        if token:
            return token

    if authorization is None:
        return None

    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        return token or None

    token = authorization.strip()
    return token or None


class AuthService(Protocol):
    def authorize_ws_hello(self, *, token: str | None) -> ProtocolValidationError | None:
        ...

    def authorize_http_send(
        self,
        *,
        authorization: str | None,
        x_acp_token: str | None,
        body_token: str | None,
    ) -> ProtocolValidationError | None:
        ...

    def authorize_ws_message(
        self, *, session_name: str | None, claimed_sender: str | None
    ) -> ProtocolValidationError | None:
        ...

    def evaluate_scope(
        self,
        *,
        scope: ScopeName,
        principal: str | None,
        surface: str,
    ) -> ScopeDecision:
        ...

    def evaluate_identity_binding(
        self,
        *,
        principal: str | None,
        claimed_sender: str | None,
        surface: str,
    ) -> ScopeDecision:
        ...

    def evaluate_acl(
        self,
        *,
        principal: str | None,
        sender: str | None,
        recipient: str | None,
        action: str | None,
        surface: str,
    ) -> ScopeDecision:
        ...

    def deny_error(
        self,
        *,
        decision: ScopeDecision,
        field: str,
    ) -> ProtocolValidationError:
        ...


class PermissiveAuthService:
    """Default auth adapter that preserves v0.1 behavior."""

    def __init__(
        self,
        *,
        required_token: str | None = None,
        scope_provider: ScopeProvider | None = None,
        auth_enforce: bool = False,
        previous_token: str | None = None,
        overlap_until: datetime | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.required_token = required_token
        self.scope_provider = scope_provider or NullScopeProvider()
        self.auth_enforce = auth_enforce
        self.previous_token = previous_token
        self.overlap_until = overlap_until
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def _token_matches_rotation_window(self, token: str) -> bool:
        if not token:
            return False
        if self.required_token is not None and token == self.required_token:
            return True
        if self.previous_token is None or self.overlap_until is None:
            return False
        if token != self.previous_token:
            return False
        return self._now_provider().astimezone(timezone.utc) <= self.overlap_until.astimezone(timezone.utc)

    def authorize_ws_hello(self, *, token: str | None) -> ProtocolValidationError | None:
        if self.required_token is None:
            return None
        if token is None:
            return build_error(INVALID_FIELD, field="token", message="token is required.")
        if not self._token_matches_rotation_window(token):
            return build_error(INVALID_FIELD, field="token", message="token is invalid.")
        return None

    def authorize_http_send(
        self,
        *,
        authorization: str | None,
        x_acp_token: str | None,
        body_token: str | None,
    ) -> ProtocolValidationError | None:
        if self.required_token is None:
            return None

        header_token = extract_http_token(authorization, x_acp_token)
        selected_token = header_token if header_token is not None else body_token
        if selected_token is None:
            return build_error(AUTH_REQUIRED, field="token", message="token is required")
        if not self._token_matches_rotation_window(selected_token):
            return build_error(AUTH_INVALID, field="token", message="token is invalid")
        return None

    def authorize_ws_message(
        self, *, session_name: str | None, claimed_sender: str | None
    ) -> ProtocolValidationError | None:
        if session_name is None or claimed_sender != session_name:
            return build_error(
                INVALID_FIELD,
                field="from",
                message="sender identity must match registered agent session.",
            )
        return None

    def evaluate_scope(
        self,
        *,
        scope: ScopeName,
        principal: str | None,
        surface: str,
    ) -> ScopeDecision:
        if principal is None:
            return ScopeDecision(
                scope=scope,
                principal=None,
                surface=surface,
                decision="deny" if self.auth_enforce else "would_deny",
                reason_code="PRINCIPAL_MISSING",
            )

        principal_scopes = self.scope_provider.get_scopes_for_principal(principal)
        if principal_scopes is None:
            return ScopeDecision(
                scope=scope,
                principal=principal,
                surface=surface,
                decision="deny" if self.auth_enforce else "would_deny",
                reason_code="PRINCIPAL_UNKNOWN",
            )

        if "*" in principal_scopes or scope in principal_scopes:
            return ScopeDecision(
                scope=scope,
                principal=principal,
                surface=surface,
                decision="allow",
                reason_code="SCOPE_GRANTED",
            )

        return ScopeDecision(
            scope=scope,
            principal=principal,
            surface=surface,
            decision="deny" if self.auth_enforce else "would_deny",
            reason_code="SCOPE_MISSING",
        )

    def evaluate_identity_binding(
        self,
        *,
        principal: str | None,
        claimed_sender: str | None,
        surface: str,
    ) -> ScopeDecision:
        if principal is None:
            return ScopeDecision(
                scope="send",
                principal=None,
                surface=surface,
                decision="deny" if self.auth_enforce else "would_deny",
                reason_code="PRINCIPAL_MISSING",
            )
        if claimed_sender is None:
            return ScopeDecision(
                scope="send",
                principal=principal,
                surface=surface,
                decision="deny" if self.auth_enforce else "would_deny",
                reason_code="SENDER_MISSING",
            )
        if principal == claimed_sender:
            return ScopeDecision(
                scope="send",
                principal=principal,
                surface=surface,
                decision="allow",
                reason_code="IDENTITY_BOUND",
            )
        return ScopeDecision(
            scope="send",
            principal=principal,
            surface=surface,
            decision="deny" if self.auth_enforce else "would_deny",
            reason_code="IDENTITY_MISMATCH",
        )

    def evaluate_acl(
        self,
        *,
        principal: str | None,
        sender: str | None,
        recipient: str | None,
        action: str | None,
        surface: str,
    ) -> ScopeDecision:
        if sender is None or recipient is None or action is None:
            return ScopeDecision(
                scope="send",
                principal=principal,
                surface=surface,
                decision="deny" if self.auth_enforce else "would_deny",
                reason_code="ACL_INPUT_INVALID",
            )

        acl_decision = self.scope_provider.get_acl_decision(
            sender=sender,
            recipient=recipient,
            action=action,
        )
        if acl_decision == "allow":
            return ScopeDecision(
                scope="send",
                principal=principal,
                surface=surface,
                decision="allow",
                reason_code="ACL_ALLOW",
            )
        reason = "ACL_DENY" if acl_decision == "deny" else "ACL_NO_RULE"
        return ScopeDecision(
            scope="send",
            principal=principal,
            surface=surface,
            decision="deny" if self.auth_enforce else "would_deny",
            reason_code=reason,
        )

    def deny_error(
        self,
        *,
        decision: ScopeDecision,
        field: str,
    ) -> ProtocolValidationError:
        message = "operation denied by policy."
        if decision.reason_code == "IDENTITY_MISMATCH":
            message = "sender identity does not match authenticated principal."
            field = "from"
        return build_error(
            AUTH_FORBIDDEN,
            field=field,
            message=message,
            details={"reason_code": decision.reason_code},
        )
