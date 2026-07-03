"""Minimal browser-session auth for Hub dashboards."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DashboardSession:
    session_id: str
    created_at: str = field(default_factory=_utc_now_iso)
    last_seen_at: str = field(default_factory=_utc_now_iso)

    def touch(self) -> None:
        self.last_seen_at = _utc_now_iso()

    def as_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
        }


class DashboardSessionStore:
    def __init__(self, *, ttl_seconds: int = 43200) -> None:
        self._sessions: dict[str, DashboardSession] = {}
        self.ttl_seconds = max(int(ttl_seconds), 1)

    def create(self) -> DashboardSession:
        session = DashboardSession(session_id=secrets.token_urlsafe(32))
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str | None) -> DashboardSession | None:
        if not isinstance(session_id, str) or not session_id.strip():
            return None
        session = self._sessions.get(session_id.strip())
        if session is None:
            return None
        if self._is_expired(session):
            self._sessions.pop(session.session_id, None)
            return None
        session.touch()
        return session

    def revoke(self, session_id: str | None) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            return
        self._sessions.pop(session_id.strip(), None)

    def count(self) -> int:
        self._purge_expired()
        return len(self._sessions)

    def _is_expired(self, session: DashboardSession) -> bool:
        normalized = session.last_seen_at[:-1] + "+00:00" if session.last_seen_at.endswith("Z") else session.last_seen_at
        try:
            last_seen_at = datetime.fromisoformat(normalized)
        except ValueError:
            return True
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
        return (_utc_now() - last_seen_at.astimezone(timezone.utc)).total_seconds() > self.ttl_seconds

    def _purge_expired(self) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if self._is_expired(session)
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


@dataclass(frozen=True)
class MemberSession:
    """The identity a member cookie resolves to — scoped to ONE coordination
    session and ONE agent, plus the member_token that identity was minted with.

    Carries NO admin capability. It holds the member_token *server-side only*
    (the client's cookie is a separate opaque random handle; the token never
    leaves the process to the browser). Storing it lets ``get_session_detail``
    re-run the SAME ``hmac.compare_digest`` re-validation as the header/query
    path on every poll — so if the member is removed and a new agent later
    rejoins under the same name (with a fresh token), the old cookie fails
    closed instead of silently resolving to the new member. The token already
    lives in the coordination store + SQLite in this process, so keeping a copy
    keyed by the cookie hash adds no new exposure surface.
    """

    session_id: str
    agent_name: str
    member_token: str


class MemberSessionStore:
    """Server-side store for httpOnly member-session cookies.

    Mirrors ``DashboardSessionStore`` but, following the managed-session
    precedent (``acp_managed.auth.session.SessionTokenManager``), the dict is
    keyed by an HMAC-SHA256 *hash* of the cookie value — the raw cookie token is
    never stored and never predictable. Each record maps a hashed cookie to
    ``{session_id, agent_name, member_token}`` (member_token server-side only,
    used to re-validate against the live coordination store per request). No
    admin flag is ever stored.

    TTL defaults to the coordination stale-session horizon (1 hour) so a cookie
    cannot outlive the window in which the underlying session is considered
    live; access is always re-validated against coordination per request.
    """

    def __init__(self, *, secret: str | None = None, ttl_seconds: int = 3600) -> None:
        # A per-instance random secret is sufficient: the hash never leaves this
        # process, so we do not need a stable configured secret across restarts
        # (a restart wipes the in-memory records anyway, invalidating cookies).
        chosen = secret if isinstance(secret, str) and secret.strip() else secrets.token_urlsafe(32)
        self._secret = chosen.encode("utf-8")
        self.ttl_seconds = max(int(ttl_seconds), 1)
        # hashed_token -> (MemberSession, created_monotonic)
        self._sessions: dict[str, tuple[MemberSession, float]] = {}

    def _hash_token(self, raw_token: str) -> str:
        return hmac.new(self._secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def create(self, session_id: str, agent_name: str, member_token: str) -> str:
        raw_token = secrets.token_urlsafe(32)
        record = MemberSession(session_id=session_id, agent_name=agent_name, member_token=member_token)
        self._sessions[self._hash_token(raw_token)] = (record, time.monotonic())
        return raw_token

    def get(self, raw_token: str | None) -> MemberSession | None:
        if not isinstance(raw_token, str) or not raw_token.strip():
            return None
        hashed = self._hash_token(raw_token.strip())
        entry = self._sessions.get(hashed)
        if entry is None:
            return None
        record, created_at = entry
        if (time.monotonic() - created_at) > self.ttl_seconds:
            self._sessions.pop(hashed, None)
            return None
        return record

    def revoke(self, raw_token: str | None) -> None:
        if not isinstance(raw_token, str) or not raw_token.strip():
            return
        self._sessions.pop(self._hash_token(raw_token.strip()), None)

    def revoke_for(self, session_id: str, agent_name: str | None = None) -> None:
        stale = [
            hashed
            for hashed, (record, _) in self._sessions.items()
            if record.session_id == session_id
            and (agent_name is None or record.agent_name == agent_name)
        ]
        for hashed in stale:
            self._sessions.pop(hashed, None)

    def count(self) -> int:
        self._purge_expired()
        return len(self._sessions)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [
            hashed
            for hashed, (_, created_at) in self._sessions.items()
            if (now - created_at) > self.ttl_seconds
        ]
        for hashed in expired:
            self._sessions.pop(hashed, None)
