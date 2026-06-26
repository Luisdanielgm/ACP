"""Minimal browser-session auth for Hub dashboards."""

from __future__ import annotations

import secrets
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
