"""Shared coordination state models and time helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_HEARTBEAT_LIVE_SECONDS = 90
_HEARTBEAT_QUIET_SECONDS = 360
_SESSION_STALE_MEMBER_SECONDS = 1800  # 30 minutes without heartbeat = stale member
_SESSION_MAX_IDLE_SECONDS = 7200  # 2 hours without any activity = session eligible for cleanup


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def heartbeat_age_seconds(value: str | None, *, now: datetime | None = None) -> int | None:
    parsed = parse_iso_utc(value)
    if parsed is None:
        return None
    reference = now or datetime.now(timezone.utc)
    delta_seconds = int(max(0, (reference - parsed).total_seconds()))
    return delta_seconds


def heartbeat_state(value: str | None, *, now: datetime | None = None) -> str:
    age_seconds = heartbeat_age_seconds(value, now=now)
    if age_seconds is None:
        return "unknown"
    if age_seconds <= _HEARTBEAT_LIVE_SECONDS:
        return "live"
    if age_seconds <= _HEARTBEAT_QUIET_SECONDS:
        return "quiet"
    return "stale"


@dataclass
class SessionMember:
    agent_name: str
    role: str
    member_token: str
    capabilities: tuple[str, ...] = ()
    delivery_mode: str = "attached"
    provider: str | None = None
    workspace_path: str | None = None
    status: str = "idle"
    status_text: str | None = None
    joined_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    last_message_at: str | None = None
    last_action: str | None = None
    current_task: str | None = None
    current_task_from: str | None = None
    current_task_at: str | None = None
    current_run: dict[str, Any] | None = None
    last_run: dict[str, Any] | None = None

    def as_payload(self, *, pending_count: int = 0, now: datetime | None = None) -> dict[str, Any]:
        current_now = now or datetime.now(timezone.utc)
        current_heartbeat_age = heartbeat_age_seconds(self.last_seen_at, now=current_now)
        return {
            "agent_name": self.agent_name,
            "role": self.role,
            "capabilities": list(self.capabilities),
            "delivery_mode": self.delivery_mode,
            "provider": self.provider,
            "workspace_path": self.workspace_path,
            "status": self.status,
            "status_text": self.status_text,
            "joined_at": self.joined_at,
            "last_seen_at": self.last_seen_at,
            "last_message_at": self.last_message_at,
            "last_action": self.last_action,
            "current_task": self.current_task,
            "current_task_from": self.current_task_from,
            "current_task_at": self.current_task_at,
            "current_run": dict(self.current_run) if isinstance(self.current_run, dict) else None,
            "last_run": dict(self.last_run) if isinstance(self.last_run, dict) else None,
            "pending_count": pending_count,
            "heartbeat_state": heartbeat_state(self.last_seen_at, now=current_now),
            "heartbeat_age_seconds": current_heartbeat_age,
        }


@dataclass
class CoordinationSession:
    session_id: str
    join_code: str
    created_by: str
    created_at: str = field(default_factory=utc_now_iso)
    title: str | None = None
    project: str | None = None
    members: dict[str, SessionMember] = field(default_factory=dict)

    def as_payload(
        self,
        *,
        pending_counts: dict[str, int] | None = None,
        include_join_code: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        counts = pending_counts or {}
        payload = {
            "session_id": self.session_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "title": self.title,
            "project": self.project,
            "members": [
                member.as_payload(pending_count=int(counts.get(member.agent_name, 0)), now=now)
                for member in sorted(self.members.values(), key=lambda item: item.agent_name)
            ],
        }
        if include_join_code:
            payload["join_code"] = self.join_code
        return payload
