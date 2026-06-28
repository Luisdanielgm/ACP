"""Persistent browser session helpers for the managed workspace layer."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedSession:
    session_id: str
    email: str
    role: str
    issued_at: int
    expires_at: int


class SessionTokenManager:
    def __init__(self, *, secret: str, ttl_seconds: int = 60 * 60 * 12) -> None:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("managed session secret is required")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = max(300, int(ttl_seconds))

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def issue_token(self) -> tuple[str, int, int]:
        now = int(time.time())
        return secrets.token_urlsafe(32), now, now + self._ttl_seconds

    def hash_token(self, token: str) -> str:
        if not isinstance(token, str) or not token:
            raise ValueError("session token is required")
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


class AgentTokenManager:
    def __init__(self, *, secret: str) -> None:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("managed agent token secret is required")
        self._secret = secret.encode("utf-8")

    def issue_token(self) -> str:
        return f"acpagt_{secrets.token_urlsafe(32)}"

    def hash_token(self, token: str) -> str:
        if not isinstance(token, str) or not token:
            raise ValueError("agent token is required")
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
