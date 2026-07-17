"""Session coordination primitives for skill-driven ACP agents."""

from __future__ import annotations

import asyncio
import hmac
import re
import secrets
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from acp.hub.coordination_state import (
    SESSION_LIFECYCLE_EPHEMERAL,
    SESSION_LIFECYCLE_MODES,
    SESSION_LIFECYCLE_PERSISTENT,
    CoordinationSession,
    SessionMember,
    heartbeat_age_seconds,
    utc_now_iso,
)
from acp.hub.coordination_store import CoordinationStore, InMemoryCoordinationStore

_SESSION_EVENT_LIMIT = 250
# Wait/heartbeat polling floods the plain last-N window until it holds ONLY
# wait events and every other dashboard filter goes empty. The store therefore
# guarantees a floor of the most recent non-noise events regardless of how
# many noise events came after them (no scan window is big enough).
_HISTORY_PROTECTED_FLOOR = 90
_HISTORY_NOISE_EVENTS = ("WAIT_STARTED", "WAIT_TIMEOUT", "WAIT_CANCELLED", "WAIT_EVICTED", "HEARTBEAT")
_PAYLOAD_PREVIEW_LIMIT = 240
_ACTION_PRIORITY = {"REPLY": 0, "TASK": 1, "INFO": 2}
_NAMED_PRIORITY = {"urgent": -2, "high": -1, "normal": 0, "low": 1}
_HEARTBEAT_EVENT_MIN_SECONDS = 60
_STALE_SESSION_CLEANUP_SECONDS = 3600  # Clean sessions where all members are stale for 1 hour
_CLEANUP_INTERVAL_SECONDS = 300  # Run cleanup at most every 5 minutes
_RUNNER_INTERRUPT_AFTER_SECONDS = 180
_SAFE_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


def _utc_now_iso() -> str:
    return utc_now_iso()


def _should_record_heartbeat(previous_seen_at: str | None, *, now: datetime) -> bool:
    age_seconds = heartbeat_age_seconds(previous_seen_at, now=now)
    return age_seconds is None or age_seconds >= _HEARTBEAT_EVENT_MIN_SECONDS


def _new_join_code() -> str:
    return secrets.token_hex(4).upper()


def _new_member_token() -> str:
    return secrets.token_urlsafe(24)


def _normalize_capabilities(value: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    seen: set[str] = set()
    capabilities: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().lower()
        if not cleaned or _SAFE_CAPABILITY.fullmatch(cleaned) is None:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            capabilities.append(cleaned)
    return tuple(capabilities)


def _payload_preview(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= _PAYLOAD_PREVIEW_LIMIT else cleaned[: _PAYLOAD_PREVIEW_LIMIT - 3] + "..."


def _message_priority(message: Mapping[str, Any]) -> tuple[int, str]:
    raw_priority = message.get("priority")
    if isinstance(raw_priority, (int, float)):
        priority_rank = int(raw_priority)
    elif isinstance(raw_priority, str) and raw_priority.strip():
        priority_rank = _NAMED_PRIORITY.get(raw_priority.strip().lower(), 0)
    else:
        action = message.get("action")
        priority_rank = _ACTION_PRIORITY.get(action if isinstance(action, str) else "", 3)
    ts = message.get("ts")
    return priority_rank, ts if isinstance(ts, str) and ts else _utc_now_iso()


class SessionAccessError(ValueError):
    pass


class SessionNotFoundError(SessionAccessError):
    """Raised when the coordination session itself no longer exists.

    Distinct from a membership/token failure so the HTTP layer can answer 404
    (session gone, e.g. closed or lost on a redeploy) instead of 403 (auth),
    letting clients tell "re-create/re-join" apart from "fix your credentials".
    """


class SessionConflictError(SessionAccessError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


WAIT_ALREADY_ACTIVE_DETAIL = (
    "This member already has an active wait/listen request. Do not run concurrent waits. "
    "If managed-join or another listener is still running, stop that process first. "
    "Turn-based LLM agents should use one loop: listen --stop-after-message --timeout-seconds 300, "
    "process one message, send REPLY or INFO, publish waiting, then listen again."
)


class SessionDashboardAccessError(ValueError):
    pass


@dataclass(frozen=True)
class WaitRegistration:
    future: asyncio.Future[dict[str, Any]]
    started_at: datetime
    expires_at: datetime
    ack_mode: str = "auto"
    lease_seconds: float = 30.0
    action: str | None = None

    def accepts_action(self, action: str) -> bool:
        return self.action is None or self.action == action.upper()

    def ttl_seconds(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        return max(0, int((self.expires_at - current).total_seconds()))


class SessionCoordinationService:
    """Coordination layer for session-oriented agent workflows."""

    def __init__(self, *, store: CoordinationStore | None = None) -> None:
        self._store = store or InMemoryCoordinationStore()
        self._waiters: dict[tuple[str, str], WaitRegistration] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup_at: datetime | None = None

    async def create_session(
        self,
        *,
        owner_agent: str,
        title: str | None = None,
        project: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        delivery_mode: str = "attached",
        provider: str | None = None,
        workspace_path: str | None = None,
        lifecycle_mode: str = SESSION_LIFECYCLE_EPHEMERAL,
    ) -> dict[str, Any]:
        async with self._lock:
            if lifecycle_mode not in SESSION_LIFECYCLE_MODES:
                raise SessionAccessError("session lifecycle_mode must be ephemeral or persistent.")
            self._ensure_agent_is_free(owner_agent)
            session_id = str(uuid4())
            join_code = self._unique_join_code()
            member_token = _new_member_token()
            member = SessionMember(
                agent_name=owner_agent,
                role="chief",
                member_token=member_token,
                capabilities=_normalize_capabilities(capabilities),
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
            session = CoordinationSession(
                session_id=session_id,
                join_code=join_code,
                created_by=owner_agent,
                title=title,
                project=project,
                lifecycle_mode=lifecycle_mode,
                members={owner_agent: member},
            )
            try:
                self._store.create_session(session)
            except sqlite3.IntegrityError as exc:
                # Cross-process race: another worker claimed this join_code or
                # agent_name between our in-process check and the INSERT.
                raise SessionAccessError("session could not be created due to a conflicting join code or agent name.") from exc
            self._record_event(session_id, event="SESSION_CREATED", actor=owner_agent, detail="session created", extra={"title": title, "project": project})
            return {
                "session_id": session_id,
                "join_code": join_code,
                "member_token": member_token,
                "member_role": member.role,
                "session": self._build_session_payload(session, include_join_code=True),
            }

    async def join_session(
        self,
        *,
        join_code: str,
        agent_name: str,
        capabilities: list[str] | tuple[str, ...] | None = None,
        delivery_mode: str = "attached",
        provider: str | None = None,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            session = self._store.get_session_by_join_code(join_code.strip().upper())
            if session is None:
                raise SessionAccessError("join code is invalid.")
            self._ensure_agent_is_free(agent_name)
            member_token = _new_member_token()
            member = SessionMember(
                agent_name=agent_name,
                role="collaborator",
                member_token=member_token,
                capabilities=_normalize_capabilities(capabilities),
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
            try:
                self._store.add_member(session.session_id, member)
            except sqlite3.IntegrityError as exc:
                # Cross-process race: another worker attached this agent_name
                # between our in-process check and the INSERT.
                raise SessionAccessError("agent is already attached to another session.") from exc
            self._record_event(session.session_id, event="SESSION_JOINED", actor=agent_name, detail="agent joined session")
            updated = self._require_session(session.session_id)
            return {
                "session_id": session.session_id,
                "join_code": updated.join_code,
                "member_token": member_token,
                "member_role": member.role,
                "session": self._build_session_payload(updated, include_join_code=True),
            }

    async def leave_session(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any]:
        async with self._lock:
            session, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            if member.role == "chief" and session.lifecycle_mode == SESSION_LIFECYCLE_PERSISTENT:
                raise SessionAccessError("persistent session chief must close explicitly instead of leaving.")
            closing_session = member.role == "chief" or len(session.members) <= 1
            if closing_session:
                detail = "chief left session" if member.role == "chief" else "last member left session"
                self._record_event(session_id, event="SESSION_CLOSED", actor=agent_name, detail=detail)
                self._close_session_locked(
                    session,
                    notice_builder=lambda affected: self._system_message(
                        session_id=session.session_id,
                        to=affected.agent_name,
                        payload_text="session closed because the chief left" if member.role == "chief" else "session closed because the last member left",
                        system_event="SESSION_CLOSED",
                        session_closed=True,
                    ),
                )
            else:
                self._record_event(session_id, event="SESSION_LEFT", actor=agent_name, detail="agent left session")
                self._remove_member_locked(
                    session_id=session.session_id,
                    agent_name=agent_name,
                    member_token=member.member_token,
                    notice=self._system_message(
                        session_id=session.session_id,
                        to=agent_name,
                        payload_text="you left the session",
                        system_event="MEMBER_LEFT",
                        session_closed=False,
                    ),
                )
            return {"status": "left", "session_id": session_id, "agent_name": agent_name, "session_closed": closing_session}

    async def cancel_wait(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any]:
        async with self._lock:
            self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            waiter = self._waiters.pop((session_id, agent_name), None)
            if waiter is not None and not waiter.future.done():
                waiter.future.set_result(
                    {
                        "message": self._system_message(
                            session_id=session_id,
                            to=agent_name,
                            payload_text="wait cancelled by member request",
                            system_event="WAIT_CANCELLED",
                            session_closed=False,
                        ),
                        "delivery": None,
                    }
                )
            self._record_event(session_id, event="WAIT_CANCELLED", actor=agent_name, detail="wait cancelled by member request")
            return {
                "status": "cancelled" if waiter is not None else "no_active_wait",
                "session_id": session_id,
                "agent_name": agent_name,
                "active_wait_cleared": waiter is not None,
            }

    async def admin_close_session(self, *, session_id: str, actor: str = "admin", detail: str | None = None) -> dict[str, Any]:
        async with self._lock:
            session = self._store.get_session(session_id)
            if session is None:
                raise SessionNotFoundError("session does not exist.")
            self._record_event(session_id, event="SESSION_CLOSED", actor=actor, detail=detail or "session closed by admin", extra={"forced": True})
            affected_members = list(session.members)
            close_message = detail or "session closed by admin"
            self._close_session_locked(
                session,
                notice_builder=lambda affected: self._system_message(
                    session_id=session.session_id,
                    to=affected.agent_name,
                    payload_text=close_message,
                    system_event="SESSION_CLOSED",
                    session_closed=True,
                    forced=True,
                    removed_by=actor,
                ),
            )
            return {"status": "closed", "session_id": session_id, "closed_by": actor, "session_closed": True, "removed_members": affected_members}

    async def admin_reset_session_messages(
        self,
        *,
        session_id: str,
        actor: str = "admin",
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Reset room messaging while preserving the durable collaboration room."""
        async with self._lock:
            session = self._store.get_session(session_id)
            if session is None:
                raise SessionNotFoundError("session does not exist.")
            cleared = self._store.reset_session_messages(session_id=session_id)
            for member in session.members.values():
                member.current_task = None
                member.status = "waiting"
                member.status_text = "room messages reset"
                self._store.update_member(session_id, member)
                notice = self._system_message(
                    session_id=session_id,
                    to=member.agent_name,
                    payload_text="room messages were reset by workspace administration",
                    system_event="MESSAGES_RESET",
                    session_closed=False,
                    forced=True,
                    removed_by=actor,
                )
                self._store.put_notice(
                    session_id=session_id,
                    agent_name=member.agent_name,
                    member_token=member.member_token,
                    notice=notice,
                )
                waiter = self._waiters.pop((session_id, member.agent_name), None)
                if waiter is not None and waiter.action is None and not waiter.future.done():
                    waiter.future.set_result({"message": dict(notice), "delivery": None})
                elif waiter is not None and waiter.action is not None and not waiter.future.done():
                    self._waiters[(session_id, member.agent_name)] = waiter
            self._record_event(
                session_id,
                event="MESSAGES_RESET",
                actor=actor,
                detail=reason or "room messages reset by workspace administrator",
                extra={**cleared, "administrative": True},
            )
            return {
                "status": "messages_reset",
                "session_id": session_id,
                "reset_by": actor,
                "reason": reason,
                **cleared,
                "preserved": ["session", "members", "wall", "files", "operator"],
            }

    async def admin_remove_member(self, *, session_id: str, agent_name: str, actor: str = "admin", detail: str | None = None) -> dict[str, Any]:
        async with self._lock:
            session = self._store.get_session(session_id)
            if session is None:
                raise SessionNotFoundError("session does not exist.")
            member = session.members.get(agent_name)
            if member is None:
                raise SessionAccessError("agent is not a member of this session.")
            if member.role == "chief" and session.lifecycle_mode == SESSION_LIFECYCLE_PERSISTENT:
                raise SessionAccessError("persistent session chief must be closed explicitly instead of disconnected.")
            closing_session = member.role == "chief" or len(session.members) <= 1
            if closing_session:
                close_message = detail or "session closed by admin after member disconnect"
                self._record_event(session_id, event="SESSION_CLOSED", actor=actor, target=agent_name, detail=close_message, extra={"forced": True, "removed_agent": agent_name})
                affected_members = list(session.members)
                self._close_session_locked(
                    session,
                    notice_builder=lambda affected: self._system_message(
                        session_id=session.session_id,
                        to=affected.agent_name,
                        payload_text=close_message,
                        system_event="SESSION_CLOSED",
                        session_closed=True,
                        forced=True,
                        removed_by=actor,
                        removed_agent=agent_name,
                    ),
                )
                return {"status": "removed", "session_id": session_id, "agent_name": agent_name, "removed_by": actor, "session_closed": True, "removed_members": affected_members}
            self._record_event(session_id, event="SESSION_LEFT", actor=actor, target=agent_name, detail=detail or "member removed by admin", extra={"forced": True, "removed_agent": agent_name})
            self._remove_member_locked(
                session_id=session.session_id,
                agent_name=agent_name,
                member_token=member.member_token,
                notice=self._system_message(
                    session_id=session.session_id,
                    to=agent_name,
                    payload_text=detail or "you were disconnected from the session by admin",
                    system_event="MEMBER_DISCONNECTED",
                    session_closed=False,
                    forced=True,
                    removed_by=actor,
                ),
            )
            return {"status": "removed", "session_id": session_id, "agent_name": agent_name, "removed_by": actor, "session_closed": False}

    async def session_snapshot(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any]:
        async with self._lock:
            session, _ = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            return self._build_session_payload(session, include_join_code=True)

    async def session_detail(
        self,
        *,
        session_id: str,
        agent_name: str | None = None,
        member_token: str | None = None,
        include_join_code: bool = True,
    ) -> dict[str, Any]:
        async with self._lock:
            session = self._store.get_session(session_id)
            if session is None:
                if agent_name is not None and member_token is not None:
                    notice = self._member_notice(session_id=session_id, agent_name=agent_name, member_token=member_token)
                    if notice is not None:
                        raise SessionAccessError(self._notice_message(notice))
                raise SessionNotFoundError("session does not exist.")
            session = self._refresh_runner_members(session)
            if agent_name is not None and member_token is not None:
                self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            elif agent_name is not None or member_token is not None:
                raise SessionDashboardAccessError("agent_name and member_token must be provided together.")
            payload = self._build_session_payload(session, include_join_code=include_join_code, refresh=False)
            payload["history"] = self._store.get_balanced_session_events(
                session_id,
                limit=_SESSION_EVENT_LIMIT,
                protected_limit=_HISTORY_PROTECTED_FLOOR,
                noise_event_types=_HISTORY_NOISE_EVENTS,
            )
            payload["summary"] = self._build_session_summary(session, refresh=False)
            return payload

    async def verify_member(self, *, session_id: str, agent_name: str, member_token: str) -> None:
        """Validate member credentials without returning session data.

        Thin wrapper over ``_authorize`` for the member-session-cookie exchange
        endpoint. Returns None on success; raises ``SessionNotFoundError`` (404)
        or ``SessionAccessError`` (403) exactly as the normal member-auth path
        does, so callers reuse the same error shapes.
        """
        async with self._lock:
            self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)

    async def cleanup_stale_sessions(self) -> list[str]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._last_cleanup_at is not None:
                elapsed = (now - self._last_cleanup_at).total_seconds()
                if elapsed < _CLEANUP_INTERVAL_SECONDS:
                    return []
            self._last_cleanup_at = now
            return self._store.cleanup_stale_sessions(stale_after_seconds=_STALE_SESSION_CLEANUP_SECONDS)

    async def prune_idempotency_older_than(self, cutoff: str) -> int:
        async with self._lock:
            return self._store.prune_idempotency_older_than(cutoff)

    async def prune_noise_events_older_than(self, cutoff: str) -> int:
        async with self._lock:
            return self._store.prune_noise_events_older_than(
                cutoff, noise_event_types=_HISTORY_NOISE_EVENTS
            )

    def close(self) -> None:
        """Release the underlying store's persistent connection, if any."""
        close = getattr(self._store, "close", None)
        if callable(close):
            close()

    async def dashboard_snapshot(self) -> dict[str, Any]:
        await self.cleanup_stale_sessions()
        async with self._lock:
            live_sessions = sorted(self._store.list_sessions(), key=lambda item: item.created_at)
            live_sessions = [self._refresh_runner_members(session) for session in live_sessions]
            pending_counts_by_session = self._store.pending_counts_for_sessions(
                [session.session_id for session in live_sessions]
            )
            sessions = [
                self._build_session_summary(
                    session,
                    pending_counts=pending_counts_by_session.get(session.session_id, {}),
                    refresh=False,
                )
                for session in live_sessions
            ]
            status_counts: Counter[str] = Counter()
            member_total = 0
            for session in live_sessions:
                for member in session.members.values():
                    status_counts[member.status] += 1
                    member_total += 1
            return {
                "sessions": sessions,
                "session_count": len(sessions),
                "member_count": member_total,
                "status_counts": {key: status_counts.get(key, 0) for key in ("idle", "waiting", "busy")},
                "generated_at": _utc_now_iso(),
            }

    async def update_status(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        status: str,
        status_text: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        delivery_mode: str | None = None,
        provider: str | None = None,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            _, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            self._apply_member_delivery_metadata(
                member,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
                capabilities=capabilities,
            )
            member.status = status
            member.status_text = status_text
            member.last_seen_at = _utc_now_iso()
            if status == "idle":
                member.current_task = None
                member.current_task_from = None
                member.current_task_at = None
            self._store.update_member(session_id, member)
            self._record_event(session_id, event="STATUS_UPDATED", actor=agent_name, status=status, status_text=status_text, detail=f"status set to {status}")
            return member.as_payload(pending_count=self._pending_count_for(session_id, agent_name))

    async def heartbeat(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        detail: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        delivery_mode: str | None = None,
        provider: str | None = None,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            _, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            previous_seen_at = member.last_seen_at
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
            self._apply_member_delivery_metadata(
                member,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
                capabilities=capabilities,
            )
            member.last_seen_at = now_iso
            if detail is not None:
                member.status_text = detail
            self._store.update_member(session_id, member)
            if _should_record_heartbeat(previous_seen_at, now=now_dt):
                self._record_event(session_id, event="HEARTBEAT", actor=agent_name, status=member.status, status_text=member.status_text, detail="heartbeat received")
            return member.as_payload(pending_count=self._pending_count_for(session_id, agent_name), now=now_dt)

    async def send_message(self, *, session_id: str, agent_name: str, member_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            session, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            destination = payload.get("to")
            is_broadcast = isinstance(destination, str) and destination.strip().lower() in {"all", "*"}
            recipients = (
                [name for name in session.members if name != agent_name]
                if is_broadcast
                else [destination] if isinstance(destination, str) else []
            )
            if not is_broadcast and (not isinstance(destination, str) or destination not in session.members):
                raise SessionAccessError("destination is not a member of this session.")
            if payload.get("from") != agent_name:
                raise SessionAccessError("sender must match the authenticated session member.")
            now = _utc_now_iso()
            action = str(payload.get("action", "INFO"))
            member.last_seen_at = now
            member.last_message_at = now
            member.last_action = action
            if action.upper() == "REPLY":
                member.current_task = None
                member.current_task_from = None
                member.current_task_at = None
                member.status = "waiting"
                member.status_text = "reply sent"
            self._store.update_member(session_id, member)
            deliveries: dict[str, str] = {}
            for recipient in recipients:
                if recipient not in session.members:
                    raise SessionAccessError("destination is not a member of this session.")
                message_payload = dict(payload)
                message_payload["to"] = recipient
                message_id = message_payload.get("id")
                if (
                    isinstance(message_id, str)
                    and message_id
                    and not self._store.record_delivery_if_new(
                        session_id=session_id,
                        recipient=recipient,
                        message_id=message_id,
                        processed_at=now,
                    )
                ):
                    # Already delivered this envelope id to this recipient in this
                    # session (a retry): skip to keep delivery at-least-once without
                    # observable duplicates (C-REL-05/06).
                    deliveries[recipient] = "duplicate"
                    continue
                waiting = self._waiters.get((session_id, recipient))
                if waiting is not None and not waiting.accepts_action(action):
                    # Keep the waiter registered: this action is not part of its
                    # server-side filter and must remain queued for another consumer.
                    waiting = None
                elif waiting is not None:
                    self._waiters.pop((session_id, recipient), None)
                destination_member = session.members[recipient]
                destination_was_busy = destination_member.status == "busy"
                previous_status_text = destination_member.status_text
                if action == "TASK" and not destination_was_busy:
                    destination_member.current_task = _payload_preview(message_payload.get("payload"))
                    destination_member.current_task_from = agent_name
                    destination_member.current_task_at = now
                if waiting is not None and not waiting.future.done():
                    destination_member.last_seen_at = now
                    destination_member.last_message_at = now
                    destination_member.last_action = action
                    if waiting.ack_mode == "explicit":
                        priority_rank, sort_ts = _message_priority(message_payload)
                        self._store.enqueue_message(
                            session_id=session_id,
                            recipient_agent_name=recipient,
                            priority_rank=priority_rank,
                            sort_ts=sort_ts,
                            message=message_payload,
                        )
                        delivery_result = self._claim_explicit_delivery(
                            session_id=session_id,
                            agent_name=recipient,
                            lease_seconds=waiting.lease_seconds,
                            action=waiting.action,
                        )
                        if delivery_result is None:
                            raise RuntimeError("queued message could not be leased")
                        # claim_next_message hands back the highest-priority
                        # AVAILABLE message for the recipient, which may be an
                        # older queued or expired-lease message rather than the
                        # one we just enqueued. The delivery is still correct
                        # (the waiter gets the right next message), but this
                        # send only counts as "immediate" when the message we
                        # sent is the one actually handed over; otherwise it
                        # stays queued behind the claimed one.
                        claimed_id = (delivery_result.get("message") or {}).get("id")
                        delivered_sent_message = claimed_id == message_id
                    else:
                        delivery_result = {"message": message_payload, "delivery": None}
                        delivered_sent_message = True
                    waiting.future.set_result(delivery_result)
                    self._store.update_member(session_id, destination_member)
                    delivery = "immediate" if delivered_sent_message else "queued"
                else:
                    priority_rank, sort_ts = _message_priority(message_payload)
                    self._store.enqueue_message(session_id=session_id, recipient_agent_name=recipient, priority_rank=priority_rank, sort_ts=sort_ts, message=message_payload)
                    delivery = "queued"
                    destination_member.status = "busy" if destination_was_busy else "waiting"
                    destination_member.status_text = previous_status_text if destination_was_busy else f"queued {action} from {agent_name}; pending {self._pending_count_for(session_id, recipient)}"
                    self._store.update_member(session_id, destination_member)
                deliveries[recipient] = delivery
                self._record_event(
                    session_id,
                    event="MESSAGE_SENT",
                    actor=agent_name,
                    target=recipient,
                    action=action,
                    message_id=message_payload.get("id"),
                    thread_id=message_payload.get("thread_id"),
                    in_reply_to=message_payload.get("in_reply_to"),
                    delivery=delivery,
                    payload_preview=_payload_preview(message_payload.get("payload")),
                    detail=f"{action} sent to {recipient}",
                )
            if is_broadcast:
                return {
                    "status": "queued",
                    "session_id": session_id,
                    "to": "all",
                    "recipients": recipients,
                    "message_id": payload.get("id"),
                    "delivery": "broadcast" if recipients else "none",
                    "deliveries": deliveries,
                }
            return {"status": "queued", "session_id": session_id, "to": recipients[0], "message_id": payload.get("id"), "delivery": deliveries[recipients[0]]}

    async def record_runner_event(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        event: str,
        run_id: str,
        detail: str | None = None,
        status_text: str | None = None,
        provider: str | None = None,
        workspace_path: str | None = None,
        task_id: str | None = None,
        outcome: str | None = None,
        summary: str | None = None,
        log_chunk: str | None = None,
        metadata: dict[str, Any] | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            _, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            self._apply_member_delivery_metadata(
                member,
                delivery_mode="runner",
                provider=provider,
                workspace_path=workspace_path,
                capabilities=capabilities,
            )
            if member.delivery_mode != "runner":
                member.delivery_mode = "runner"
            now_iso = _utc_now_iso()
            event_name = event.strip().upper()
            extra: dict[str, Any] = {"run_id": run_id}
            if provider:
                extra["provider"] = provider
            if workspace_path:
                extra["workspace_path"] = workspace_path
            if task_id:
                extra["task_id"] = task_id
            if outcome:
                extra["outcome"] = outcome
            if summary:
                extra["summary"] = summary
            if metadata:
                extra["metadata"] = dict(metadata)

            if event_name == "RUN_STARTED":
                current_run = {
                    "run_id": run_id,
                    "started_at": now_iso,
                    "status": "running",
                    "provider": member.provider,
                    "workspace_path": member.workspace_path,
                }
                if task_id:
                    current_run["task_id"] = task_id
                if summary:
                    current_run["summary"] = summary
                if metadata:
                    current_run["metadata"] = dict(metadata)
                member.current_run = current_run
                member.status = "busy"
                member.status_text = status_text or detail or f"runner executing via {member.provider or 'provider'}"
            elif event_name == "RUN_LOG":
                if member.current_run is None or str(member.current_run.get("run_id")) != run_id:
                    member.current_run = {
                        "run_id": run_id,
                        "started_at": now_iso,
                        "status": "running",
                        "provider": member.provider,
                        "workspace_path": member.workspace_path,
                    }
                if summary:
                    member.current_run["summary"] = summary
                if metadata:
                    member.current_run["metadata"] = dict(metadata)
                member.current_run["last_log_at"] = now_iso
                if log_chunk:
                    member.current_run["last_log_preview"] = _payload_preview(log_chunk)
                    extra["log_preview"] = _payload_preview(log_chunk)
                member.status = "busy"
                if status_text or detail:
                    member.status_text = status_text or detail
            elif event_name == "RUN_FINISHED":
                completed_run = dict(member.current_run) if isinstance(member.current_run, dict) else {"run_id": run_id}
                completed_run["run_id"] = run_id
                completed_run["finished_at"] = now_iso
                completed_run["status"] = "finished"
                completed_run["outcome"] = outcome or "success"
                completed_run["provider"] = member.provider
                completed_run["workspace_path"] = member.workspace_path
                if task_id:
                    completed_run["task_id"] = task_id
                if summary:
                    completed_run["summary"] = summary
                if metadata:
                    completed_run["metadata"] = dict(metadata)
                member.last_run = completed_run
                member.current_run = None
                member.status = "waiting"
                member.status_text = status_text or detail or f"runner finished with {completed_run['outcome']}"
            elif event_name == "RUN_REPLY_SENT":
                last_run = dict(member.last_run) if isinstance(member.last_run, dict) else {"run_id": run_id}
                last_run["run_id"] = run_id
                last_run["reply_sent_at"] = now_iso
                if task_id:
                    last_run["task_id"] = task_id
                if summary:
                    last_run["summary"] = summary
                if outcome:
                    last_run["outcome"] = outcome
                member.last_run = last_run
                member.current_task = None
                member.current_task_from = None
                member.current_task_at = None
                member.status = "waiting"
                member.status_text = status_text or detail or "runner reply sent"
            elif event_name == "RUN_INTERRUPTED":
                interrupted_run = dict(member.current_run) if isinstance(member.current_run, dict) else {"run_id": run_id}
                interrupted_run["run_id"] = run_id
                interrupted_run["finished_at"] = now_iso
                interrupted_run["status"] = "interrupted"
                interrupted_run["outcome"] = outcome or "interrupted"
                interrupted_run["provider"] = member.provider
                interrupted_run["workspace_path"] = member.workspace_path
                if summary:
                    interrupted_run["summary"] = summary
                if metadata:
                    interrupted_run["metadata"] = dict(metadata)
                member.last_run = interrupted_run
                member.current_run = None
                member.status = "waiting"
                member.status_text = status_text or detail or "runner interrupted"
            else:
                raise SessionAccessError("runner event is invalid.")

            member.last_seen_at = now_iso
            self._store.update_member(session_id, member)
            self._record_event(
                session_id,
                event=event_name,
                actor=agent_name,
                target=agent_name,
                detail=detail or event_name.lower().replace("_", " "),
                status=member.status,
                status_text=member.status_text,
                extra=extra,
                payload_preview=_payload_preview(log_chunk),
            )
            return member.as_payload(pending_count=self._pending_count_for(session_id, agent_name))

    @staticmethod
    def _apply_delivered_task(member: SessionMember, message: dict[str, Any]) -> None:
        # send_message only stamps current_task when the recipient was free at
        # send time; a TASK that sat in the queue must refresh these fields at
        # delivery, or the member shows "processing TASK" with a stale task.
        if str(message.get("action") or "").upper() != "TASK":
            return
        member.current_task = _payload_preview(message.get("payload"))
        member.current_task_from = str(message.get("from") or "") or None
        member.current_task_at = _utc_now_iso()

    async def wait_for_message(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        timeout_seconds: float,
        ack_mode: str = "auto",
        lease_seconds: float = 30.0,
        action: str | None = None,
    ) -> dict[str, Any] | None:
        wait_action = action.upper() if isinstance(action, str) and action else None
        async with self._lock:
            notice = self._member_notice(session_id=session_id, agent_name=agent_name, member_token=member_token)
            if notice is not None:
                if wait_action is not None and notice.get("system_event"):
                    # System INFO notices are outside an action-filtered queue;
                    # do not hand one to a TASK-only bridge.
                    self._store.clear_notice(
                        session_id=session_id,
                        agent_name=agent_name,
                        member_token=member_token,
                    )
                    notice = None
                if notice is not None and notice.get("system_event") == "MESSAGES_RESET":
                    self._store.clear_notice(
                        session_id=session_id,
                        agent_name=agent_name,
                        member_token=member_token,
                    )
                if notice is not None:
                    return {"message": dict(notice), "delivery": None}
            _, member = self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            self._mark_member_waiting_if_available(session_id=session_id, agent_name=agent_name, member=member)
            if ack_mode == "explicit":
                delivery_result = self._claim_explicit_delivery(
                    session_id=session_id,
                    agent_name=agent_name,
                    lease_seconds=lease_seconds,
                    action=wait_action,
                )
            else:
                message = self._store.dequeue_next_message(session_id=session_id, recipient_agent_name=agent_name, action=wait_action)
                delivery_result = None if message is None else {"message": message, "delivery": None}
            if delivery_result is not None:
                message = delivery_result["message"]
                member.status = "busy"
                member.status_text = f"processing {message.get('action', 'INFO')}"
                member.last_seen_at = _utc_now_iso()
                self._apply_delivered_task(member, message)
                self._store.update_member(session_id, member)
                self._record_event(
                    session_id,
                    event="MESSAGE_DELIVERED",
                    actor=message.get("from"),
                    target=agent_name,
                    action=message.get("action"),
                    message_id=message.get("id"),
                    thread_id=message.get("thread_id"),
                    in_reply_to=message.get("in_reply_to"),
                    payload_preview=_payload_preview(message.get("payload")),
                    delivery="leased" if delivery_result["delivery"] is not None else "dequeued",
                    detail=f"{message.get('action', 'INFO')} delivered to waiting agent",
                )
                return delivery_result
            queue_key = (session_id, agent_name)
            existing_waiter = self._waiters.get(queue_key)
            if existing_waiter is not None and not existing_waiter.future.done():
                ttl_seconds = existing_waiter.ttl_seconds()
                if ttl_seconds <= 0:
                    # The previous wait already outlived its declared lifetime but
                    # its awaiting coroutine has not reaped it yet (client died
                    # mid-wait, or the event loop was starved). Treat it as a
                    # zombie and evict it so the member can listen again instead
                    # of being blocked behind a dead wait. The orphaned future is
                    # left to resolve via its own (already-elapsed) timeout.
                    self._waiters.pop(queue_key, None)
                    self._record_event(
                        session_id,
                        event="WAIT_EVICTED",
                        actor=agent_name,
                        detail="evicted expired wait registration before starting a new wait",
                    )
                else:
                    raise SessionConflictError(
                        f"{WAIT_ALREADY_ACTIVE_DETAIL} Existing wait TTL: {ttl_seconds}s.",
                        details={"wait_ttl_seconds": ttl_seconds},
                    )
            now_dt = datetime.now(timezone.utc)
            waiter = asyncio.get_running_loop().create_future()
            self._waiters[queue_key] = WaitRegistration(
                future=waiter,
                started_at=now_dt,
                expires_at=datetime.fromtimestamp(now_dt.timestamp() + max(timeout_seconds, 0.1), tz=timezone.utc),
                ack_mode=ack_mode,
                lease_seconds=lease_seconds,
                action=wait_action,
            )
        try:
            delivery_result = await asyncio.wait_for(waiter, timeout=max(timeout_seconds, 0.1))
        except TimeoutError:
            async with self._lock:
                current = self._waiters.get((session_id, agent_name))
                if current is not None and current.future is waiter:
                    self._waiters.pop((session_id, agent_name), None)
                session = self._store.get_session(session_id)
                member = session.members.get(agent_name) if session is not None else None
                if member is not None:
                    if member.status != "busy":
                        member.status = "waiting"
                        member.status_text = "waiting for session activity"
                        member.last_seen_at = _utc_now_iso()
                        self._store.update_member(session_id, member)
                    self._record_event(session_id, event="WAIT_TIMEOUT", actor=agent_name, detail="wait ended without new message")
            return None
        except asyncio.CancelledError:
            async with self._lock:
                current = self._waiters.get((session_id, agent_name))
                if current is not None and current.future is waiter:
                    self._waiters.pop((session_id, agent_name), None)
                    self._record_event(session_id, event="WAIT_CANCELLED", actor=agent_name, detail="wait request cancelled by client disconnect")
                elif waiter.done() and not waiter.cancelled() and waiter.exception() is None:
                    # The sender already resolved this wait, but the request task
                    # was cancelled before the coroutine could return the result.
                    # An auto-ack message lives ONLY inside this future (send never
                    # persists it on the immediate-handoff path) — re-queue it so
                    # it is not silently lost. Explicit-ack deliveries stay leased
                    # in the store and redeliver on lease expiry; system notices
                    # are persisted separately and must not be re-queued.
                    orphaned = waiter.result()
                    message = (orphaned or {}).get("message")
                    if (
                        isinstance(message, dict)
                        and (orphaned or {}).get("delivery") is None
                        and not message.get("system_event")
                    ):
                        priority_rank, sort_ts = _message_priority(message)
                        self._store.enqueue_message(
                            session_id=session_id,
                            recipient_agent_name=agent_name,
                            priority_rank=priority_rank,
                            sort_ts=sort_ts,
                            message=message,
                        )
                        self._record_event(
                            session_id,
                            event="WAIT_CANCELLED",
                            actor=agent_name,
                            message_id=message.get("id"),
                            detail="wait cancelled after delivery; message re-queued for next wait",
                        )
            raise
        async with self._lock:
            message = delivery_result["message"]
            session = self._store.get_session(session_id)
            member = session.members.get(agent_name) if session is not None else None
            if member is not None:
                member.status = "busy"
                member.status_text = f"processing {message.get('action', 'INFO')}"
                member.last_seen_at = _utc_now_iso()
                self._apply_delivered_task(member, message)
                self._store.update_member(session_id, member)
            self._record_event(
                session_id,
                event="MESSAGE_DELIVERED",
                actor=message.get("from"),
                target=agent_name,
                action=message.get("action"),
                message_id=message.get("id"),
                thread_id=message.get("thread_id"),
                in_reply_to=message.get("in_reply_to"),
                payload_preview=_payload_preview(message.get("payload")),
                delivery="leased" if delivery_result["delivery"] is not None else "immediate",
                detail=f"{message.get('action', 'INFO')} delivered through active wait",
            )
        return delivery_result

    async def notify_wall_post(
        self,
        *,
        session_id: str,
        author_name: str,
        preview: str,
    ) -> dict[str, Any] | None:
        """Record a WALL_POSTED event and wake live waiters with a system note.

        The wall is durable context: members blocked in wait learn about a new
        post immediately instead of only at their next connect. The note is
        one-shot (never queued for absent members — they get the full wall in
        their connect response).
        """
        async with self._lock:
            session = self._store.get_session(session_id)
            if session is None:
                return None
            now = _utc_now_iso()
            body_preview = _payload_preview(preview)
            self._record_event(
                session_id,
                event="WALL_POSTED",
                actor=author_name,
                payload_preview=body_preview,
                detail="room wall updated",
            )
            woken: list[str] = []
            for member_name in list(session.members):
                if member_name == author_name:
                    continue
                waiting = self._waiters.get((session_id, member_name))
                if waiting is None or waiting.future.done():
                    continue
                if waiting.action is not None:
                    # Action-filtered waits are leased only from the message
                    # queue; an INFO wall notice must not wake a TASK-only bridge.
                    continue
                self._waiters.pop((session_id, member_name), None)
                waiting.future.set_result(
                    {
                        "message": {
                            "system_event": "WALL_POSTED",
                            "from": author_name,
                            "action": "INFO",
                            "payload": (
                                f"Room wall updated by {author_name}: {body_preview} "
                                "Read the full wall with room-wall list."
                            ),
                            "ts": now,
                        },
                        "delivery": None,
                    }
                )
                woken.append(member_name)
            return {"event": "WALL_POSTED", "woken": woken}

    async def acknowledge_message(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        message_id: str,
        receipt_handle: str,
    ) -> int:
        async with self._lock:
            self._authorize(session_id=session_id, agent_name=agent_name, member_token=member_token)
            acknowledged = self._store.acknowledge_message(
                session_id=session_id,
                recipient_agent_name=agent_name,
                message_id=message_id,
                receipt_handle=receipt_handle,
                now=_utc_now_iso(),
            )
            if not acknowledged:
                raise SessionConflictError("delivery receipt is invalid, expired, or already acknowledged")
            pending_count = self._pending_count_for(session_id, agent_name)
            self._record_event(
                session_id,
                event="MESSAGE_ACKNOWLEDGED",
                actor=agent_name,
                target=agent_name,
                message_id=message_id,
                delivery="acknowledged",
                detail="message delivery acknowledged by recipient",
            )
            return pending_count

    def _claim_explicit_delivery(
        self,
        *,
        session_id: str,
        agent_name: str,
        lease_seconds: float,
        action: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        receipt_handle = secrets.token_urlsafe(24)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        message = self._store.claim_next_message(
            session_id=session_id,
            recipient_agent_name=agent_name,
            receipt_handle=receipt_handle,
            leased_until=lease_expires_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            now=now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            action=action,
        )
        if message is None:
            return None
        return {
            "message": dict(message),
            "delivery": {
                "ack_required": True,
                "message_id": str(message.get("id")),
                "receipt_handle": receipt_handle,
                "lease_expires_at": lease_expires_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            },
        }

    def _build_session_payload(
        self,
        session: CoordinationSession,
        *,
        include_join_code: bool,
        pending_counts: dict[str, int] | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        if refresh:
            session = self._refresh_runner_members(session)
        if pending_counts is None:
            pending_counts = self._store.pending_counts_for_session(session.session_id)
        return session.as_payload(pending_counts=pending_counts, include_join_code=include_join_code, now=datetime.now(timezone.utc))

    def _build_session_summary(
        self,
        session: CoordinationSession,
        *,
        pending_counts: dict[str, int] | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        if refresh:
            session = self._refresh_runner_members(session)
        if pending_counts is None:
            pending_counts = self._store.pending_counts_for_session(session.session_id)
        members = self._build_session_payload(session, include_join_code=False, pending_counts=pending_counts, refresh=False)["members"]
        status_counts: Counter[str] = Counter(member["status"] for member in members)
        last_event_at = self._store.last_session_event_ts(session.session_id)
        history_size = self._store.count_session_events(session.session_id)
        return {
            "session_id": session.session_id,
            "created_by": session.created_by,
            "created_at": session.created_at,
            "title": session.title,
            "project": session.project,
            "lifecycle_mode": session.lifecycle_mode,
            "member_count": len(members),
            "members": members,
            "pending_total": sum(pending_counts.values()),
            "pending_counts": pending_counts,
            "status_counts": {key: status_counts.get(key, 0) for key in ("idle", "waiting", "busy")},
            "last_event_at": last_event_at if last_event_at is not None else session.created_at,
            "history_size": history_size,
        }

    def _pending_count_for(self, session_id: str, agent_name: str) -> int:
        return self._store.pending_count(session_id=session_id, agent_name=agent_name)

    def _mark_member_waiting_if_available(self, *, session_id: str, agent_name: str, member: SessionMember) -> None:
        if member.status == "busy":
            return
        member.status = "waiting"
        member.status_text = "waiting for session activity"
        member.last_seen_at = _utc_now_iso()
        self._store.update_member(session_id, member)
        self._record_event(session_id, event="WAIT_STARTED", actor=agent_name, detail="agent entered wait state")

    def _record_event(
        self,
        session_id: str,
        *,
        event: str,
        actor: Any = None,
        target: Any = None,
        action: Any = None,
        detail: str | None = None,
        status: str | None = None,
        status_text: str | None = None,
        message_id: Any = None,
        thread_id: Any = None,
        in_reply_to: Any = None,
        delivery: str | None = None,
        payload_preview: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"event_id": str(uuid4()), "ts": _utc_now_iso(), "event": event}
        if isinstance(actor, str) and actor:
            payload["actor"] = actor
        if isinstance(target, str) and target:
            payload["target"] = target
        if isinstance(action, str) and action:
            payload["action"] = action
        if detail:
            payload["detail"] = detail
        if status:
            payload["status"] = status
        if status_text:
            payload["status_text"] = status_text
        if isinstance(message_id, str) and message_id:
            payload["message_id"] = message_id
        if isinstance(thread_id, str) and thread_id:
            payload["thread_id"] = thread_id
        if isinstance(in_reply_to, str) and in_reply_to:
            payload["in_reply_to"] = in_reply_to
        if delivery:
            payload["delivery"] = delivery
        if payload_preview:
            payload["payload_preview"] = payload_preview
        if extra:
            payload["extra"] = dict(extra)
        self._store.append_event(session_id, payload)

    def _unique_join_code(self) -> str:
        code = _new_join_code()
        while self._store.get_session_by_join_code(code) is not None:
            code = _new_join_code()
        return code

    def _remove_member_locked(self, *, session_id: str, agent_name: str, member_token: str, notice: dict[str, Any]) -> None:
        self._store.put_notice(session_id=session_id, agent_name=agent_name, member_token=member_token, notice=notice)
        self._store.remove_member(session_id, agent_name)
        waiter = self._waiters.pop((session_id, agent_name), None)
        if waiter is not None and not waiter.future.done():
            waiter.future.set_result({"message": dict(notice), "delivery": None})

    def _close_session_locked(self, session: CoordinationSession, *, notice_builder: Any) -> None:
        for affected_member in list(session.members.values()):
            self._remove_member_locked(
                session_id=session.session_id,
                agent_name=affected_member.agent_name,
                member_token=affected_member.member_token,
                notice=notice_builder(affected_member),
            )
        self._store.delete_session(session.session_id)

    def _system_message(
        self,
        *,
        session_id: str,
        to: str,
        payload_text: str = "session closed",
        system_event: str = "SESSION_CLOSED",
        session_closed: bool = True,
        forced: bool = False,
        removed_by: str | None = None,
        removed_agent: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "MSG",
            "id": str(uuid4()),
            "ts": _utc_now_iso(),
            "from": "system",
            "to": to,
            "action": "INFO",
            "payload": payload_text,
            "session_id": session_id,
            "system_event": system_event,
            "session_closed": session_closed,
        }
        if forced:
            payload["forced"] = True
        if isinstance(removed_by, str) and removed_by:
            payload["removed_by"] = removed_by
        if isinstance(removed_agent, str) and removed_agent:
            payload["removed_agent"] = removed_agent
        return payload

    def _member_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None:
        return self._store.get_notice(session_id=session_id, agent_name=agent_name, member_token=member_token)

    def _notice_message(self, notice: Mapping[str, Any]) -> str:
        payload_text = notice.get("payload")
        return payload_text if isinstance(payload_text, str) and payload_text.strip() else "session access is no longer available."

    def _ensure_agent_is_free(self, agent_name: str) -> None:
        if self._store.is_agent_attached(agent_name):
            raise SessionAccessError("agent is already attached to another session.")

    def _authorize(self, *, session_id: str, agent_name: str, member_token: str) -> tuple[CoordinationSession, SessionMember]:
        session = self._store.get_session(session_id)
        if session is None:
            notice = self._member_notice(session_id=session_id, agent_name=agent_name, member_token=member_token)
            if notice is not None:
                raise SessionAccessError(self._notice_message(notice))
            raise SessionNotFoundError("session does not exist.")
        session = self._refresh_runner_members(session)
        member = session.members.get(agent_name)
        if member is None:
            notice = self._member_notice(session_id=session_id, agent_name=agent_name, member_token=member_token)
            if notice is not None:
                raise SessionAccessError(self._notice_message(notice))
            raise SessionAccessError("agent is not a member of this session.")
        if not hmac.compare_digest(member.member_token, member_token):
            raise SessionAccessError("member token is invalid.")
        return session, member

    def _require_session(self, session_id: str) -> CoordinationSession:
        session = self._store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError("session does not exist.")
        return self._refresh_runner_members(session)

    def _apply_member_delivery_metadata(
        self,
        member: SessionMember,
        *,
        delivery_mode: str | None = None,
        provider: str | None = None,
        workspace_path: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        if isinstance(delivery_mode, str) and delivery_mode.strip():
            member.delivery_mode = delivery_mode.strip().lower()
        if provider is not None:
            member.provider = provider
        if workspace_path is not None:
            member.workspace_path = workspace_path
        if capabilities is not None:
            member.capabilities = _normalize_capabilities(capabilities)

    def _refresh_runner_members(self, session: CoordinationSession) -> CoordinationSession:
        now = datetime.now(timezone.utc)
        changed = False
        for member in session.members.values():
            if member.delivery_mode != "runner":
                continue
            if not isinstance(member.current_run, dict):
                continue
            age_seconds = heartbeat_age_seconds(member.last_seen_at, now=now)
            if age_seconds is None or age_seconds < _RUNNER_INTERRUPT_AFTER_SECONDS:
                continue
            interrupted_run = dict(member.current_run)
            interrupted_run["finished_at"] = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
            interrupted_run["status"] = "interrupted"
            interrupted_run["outcome"] = "interrupted"
            interrupted_run.setdefault("summary", "runner heartbeat went stale")
            member.last_run = interrupted_run
            member.current_run = None
            member.status = "waiting"
            member.status_text = "runner interrupted; waiting for recovery"
            self._store.update_member(session.session_id, member)
            self._record_event(
                session.session_id,
                event="RUN_INTERRUPTED",
                actor=member.agent_name,
                target=member.agent_name,
                detail="runner heartbeat went stale during an active run",
                status=member.status,
                status_text=member.status_text,
                extra={"run_id": interrupted_run.get("run_id"), "outcome": "interrupted"},
            )
            changed = True
        if not changed:
            return session
        refreshed = self._store.get_session(session.session_id)
        return refreshed if refreshed is not None else session
