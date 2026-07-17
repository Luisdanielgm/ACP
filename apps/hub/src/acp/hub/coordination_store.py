"""Coordination state stores for session-oriented workflows."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol
from uuid import uuid4

from acp.hub.coordination_state import (
    SESSION_LIFECYCLE_PERSISTENT,
    CoordinationSession,
    SessionMember,
)
from acp.hub.idempotency import prune_older_than, record_if_new
from acp.hub.sqlite_support import connect


def _clone_run_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return dict(value)


def _decode_optional_json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


def _decode_capabilities(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    seen: set[str] = set()
    capabilities: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            capabilities.append(cleaned)
    return tuple(capabilities)


def _encode_capabilities(value: tuple[str, ...] | list[str] | None) -> str:
    items = list(value or ())
    return json.dumps(items, sort_keys=True, separators=(",", ":"))


def _member_from_row(row: sqlite3.Row) -> SessionMember:
    return SessionMember(
        agent_name=str(row["agent_name"]),
        role=str(row["role"]),
        member_token=str(row["member_token"]),
        capabilities=_decode_capabilities(row["capabilities_json"]),
        delivery_mode=str(row["delivery_mode"]) if row["delivery_mode"] is not None else "attached",
        provider=str(row["provider"]) if row["provider"] is not None else None,
        workspace_path=str(row["workspace_path"]) if row["workspace_path"] is not None else None,
        status=str(row["status"]),
        status_text=str(row["status_text"]) if row["status_text"] is not None else None,
        joined_at=str(row["joined_at"]),
        last_seen_at=str(row["last_seen_at"]),
        last_message_at=str(row["last_message_at"]) if row["last_message_at"] is not None else None,
        last_action=str(row["last_action"]) if row["last_action"] is not None else None,
        current_task=str(row["current_task"]) if row["current_task"] is not None else None,
        current_task_from=str(row["current_task_from"]) if row["current_task_from"] is not None else None,
        current_task_at=str(row["current_task_at"]) if row["current_task_at"] is not None else None,
        current_run=_decode_optional_json_object(row["current_run_json"]),
        last_run=_decode_optional_json_object(row["last_run_json"]),
    )


class CoordinationStore(Protocol):
    def create_session(self, session: CoordinationSession) -> None: ...

    def get_session(self, session_id: str) -> CoordinationSession | None: ...

    def get_session_by_join_code(self, join_code: str) -> CoordinationSession | None: ...

    def list_sessions(self) -> list[CoordinationSession]: ...

    def is_agent_attached(self, agent_name: str) -> bool: ...

    def add_member(self, session_id: str, member: SessionMember) -> None: ...

    def update_member(self, session_id: str, member: SessionMember) -> None: ...

    def remove_member(self, session_id: str, agent_name: str) -> None: ...

    def delete_session(self, session_id: str) -> None: ...

    def enqueue_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        priority_rank: int,
        sort_ts: str,
        message: dict[str, Any],
    ) -> None: ...

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str, action: str | None = None) -> dict[str, Any] | None: ...

    def claim_next_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        receipt_handle: str,
        leased_until: str,
        now: str,
        action: str | None = None,
    ) -> dict[str, Any] | None: ...

    def acknowledge_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        message_id: str,
        receipt_handle: str,
        now: str,
    ) -> bool: ...

    def pending_count(self, *, session_id: str, agent_name: str) -> int: ...

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]: ...

    def pending_counts_for_sessions(self, session_ids: list[str]) -> dict[str, dict[str, int]]: ...

    def clear_pending(self, *, session_id: str, agent_name: str) -> None: ...

    def reset_session_messages(self, *, session_id: str) -> dict[str, int]: ...

    def record_delivery_if_new(
        self,
        *,
        session_id: str,
        recipient: str,
        message_id: str,
        processed_at: str,
    ) -> bool: ...

    def append_event(self, session_id: str, event_payload: dict[str, Any]) -> None: ...

    def get_session_events(self, session_id: str, *, limit: int) -> list[dict[str, Any]]: ...

    def get_balanced_session_events(
        self,
        session_id: str,
        *,
        limit: int,
        protected_limit: int,
        noise_event_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...

    def count_session_events(self, session_id: str) -> int: ...

    def prune_noise_events_older_than(
        self, cutoff: str, *, noise_event_types: tuple[str, ...]
    ) -> int: ...

    def last_session_event_ts(self, session_id: str) -> str | None: ...

    def put_notice(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        notice: dict[str, Any],
    ) -> None: ...

    def get_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None: ...

    def clear_notice(self, *, session_id: str, agent_name: str, member_token: str) -> None: ...

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]: ...

    def prune_idempotency_older_than(self, cutoff: str) -> int: ...


@dataclass
class InMemoryCoordinationStore:
    _sessions: dict[str, CoordinationSession] = field(default_factory=dict)
    _sessions_by_code: dict[str, str] = field(default_factory=dict)
    _agent_to_session: dict[str, str] = field(default_factory=dict)
    _pending_messages: dict[tuple[str, str], deque[dict[str, Any]]] = field(default_factory=dict)
    _session_events: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)
    _member_notices: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    # (session_id, recipient, message_id) -> processed_at, so the ledger can be
    # pruned by time like the SQLite store instead of leaking for the life of a
    # never-deleted session.
    _delivered: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def create_session(self, session: CoordinationSession) -> None:
        self._sessions[session.session_id] = session
        self._sessions_by_code[session.join_code] = session.session_id
        for member in session.members.values():
            self._agent_to_session[member.agent_name] = session.session_id

    def get_session(self, session_id: str) -> CoordinationSession | None:
        session = self._sessions.get(session_id)
        return self._clone_session(session)

    def get_session_by_join_code(self, join_code: str) -> CoordinationSession | None:
        session_id = self._sessions_by_code.get(join_code)
        if session_id is None:
            return None
        return self.get_session(session_id)

    def list_sessions(self) -> list[CoordinationSession]:
        return [self._clone_session(session) for session in self._sessions.values()]

    def is_agent_attached(self, agent_name: str) -> bool:
        return agent_name in self._agent_to_session

    def add_member(self, session_id: str, member: SessionMember) -> None:
        session = self._sessions[session_id]
        session.members[member.agent_name] = member
        self._agent_to_session[member.agent_name] = session_id

    def update_member(self, session_id: str, member: SessionMember) -> None:
        session = self._sessions[session_id]
        session.members[member.agent_name] = member
        self._agent_to_session[member.agent_name] = session_id

    def remove_member(self, session_id: str, agent_name: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.members.pop(agent_name, None)
        self._agent_to_session.pop(agent_name, None)
        self._pending_messages.pop((session_id, agent_name), None)

    def delete_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        self._sessions_by_code.pop(session.join_code, None)
        for agent_name in list(session.members):
            self._agent_to_session.pop(agent_name, None)
            self._pending_messages.pop((session_id, agent_name), None)
        self._delivered = {key: ts for key, ts in self._delivered.items() if key[0] != session_id}

    def enqueue_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        priority_rank: int,
        sort_ts: str,
        message: dict[str, Any],
    ) -> None:
        payload = dict(message)
        payload["_priority_rank"] = priority_rank
        payload["_sort_ts"] = sort_ts
        self._pending_messages.setdefault((session_id, recipient_agent_name), deque()).append(payload)

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str, action: str | None = None) -> dict[str, Any] | None:
        queue = self._pending_messages.get((session_id, recipient_agent_name))
        if not queue:
            return None
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        available = [
            (index, message)
            for index, message in enumerate(queue)
            if (not message.get("_leased_until") or str(message["_leased_until"]) <= now)
            and (action is None or str(message.get("action") or "").upper() == action)
        ]
        if not available:
            return None
        best_index, best_message = available[0]
        best_key = (int(best_message.get("_priority_rank", 0)), str(best_message.get("_sort_ts", "")))
        for index, message in available[1:]:
            key = (int(message.get("_priority_rank", 0)), str(message.get("_sort_ts", "")))
            if key < best_key:
                best_index = index
                best_key = key
        selected = dict(queue[best_index])
        del queue[best_index]
        if not queue:
            self._pending_messages.pop((session_id, recipient_agent_name), None)
        selected.pop("_priority_rank", None)
        selected.pop("_sort_ts", None)
        return selected

    def claim_next_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        receipt_handle: str,
        leased_until: str,
        now: str,
        action: str | None = None,
    ) -> dict[str, Any] | None:
        queue = self._pending_messages.get((session_id, recipient_agent_name))
        if not queue:
            return None
        available = [
            (index, message)
            for index, message in enumerate(queue)
            if (not message.get("_leased_until") or str(message["_leased_until"]) <= now)
            and (action is None or str(message.get("action") or "").upper() == action)
        ]
        if not available:
            return None
        best_index, _ = min(
            available,
            key=lambda item: (
                int(item[1].get("_priority_rank", 0)),
                str(item[1].get("_sort_ts", "")),
                item[0],
            ),
        )
        queue[best_index]["_receipt_handle"] = receipt_handle
        queue[best_index]["_leased_until"] = leased_until
        selected = dict(queue[best_index])
        for key in ("_priority_rank", "_sort_ts", "_receipt_handle", "_leased_until"):
            selected.pop(key, None)
        return selected

    def acknowledge_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        message_id: str,
        receipt_handle: str,
        now: str,
    ) -> bool:
        queue_key = (session_id, recipient_agent_name)
        queue = self._pending_messages.get(queue_key)
        if not queue:
            return False
        for index, message in enumerate(queue):
            if (
                str(message.get("id")) == message_id
                and message.get("_receipt_handle") == receipt_handle
                and str(message.get("_leased_until") or "") > now
            ):
                del queue[index]
                if not queue:
                    self._pending_messages.pop(queue_key, None)
                return True
        return False

    def pending_count(self, *, session_id: str, agent_name: str) -> int:
        return len(self._pending_messages.get((session_id, agent_name), ()))

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for (queued_session_id, agent_name), queue in self._pending_messages.items():
            if queued_session_id == session_id:
                counts[agent_name] = len(queue)
        return counts

    def pending_counts_for_sessions(self, session_ids: list[str]) -> dict[str, dict[str, int]]:
        wanted = set(session_ids)
        counts: dict[str, dict[str, int]] = {}
        for (queued_session_id, agent_name), queue in self._pending_messages.items():
            if queued_session_id in wanted:
                counts.setdefault(queued_session_id, {})[agent_name] = len(queue)
        return counts

    def clear_pending(self, *, session_id: str, agent_name: str) -> None:
        self._pending_messages.pop((session_id, agent_name), None)

    def reset_session_messages(self, *, session_id: str) -> dict[str, int]:
        queue_keys = [key for key in self._pending_messages if key[0] == session_id]
        pending_count = sum(len(self._pending_messages[key]) for key in queue_keys)
        for key in queue_keys:
            self._pending_messages.pop(key, None)
        before_events = list(self._session_events.get(session_id, ()))
        kept_events = [
            event
            for event in before_events
            if str(event.get("event") or "")
            not in {"MESSAGE_SENT", "MESSAGE_DELIVERED", "MESSAGE_ACKNOWLEDGED"}
        ]
        removed_events = len(before_events) - len(kept_events)
        self._session_events[session_id] = deque(kept_events)
        delivered_count = sum(1 for key in self._delivered if key[0] == session_id)
        self._delivered = {key: ts for key, ts in self._delivered.items() if key[0] != session_id}
        return {
            "cleared_pending_messages": pending_count,
            "cleared_message_events": removed_events,
            "cleared_delivery_ids": delivered_count,
        }

    def record_delivery_if_new(
        self,
        *,
        session_id: str,
        recipient: str,
        message_id: str,
        processed_at: str,
    ) -> bool:
        key = (session_id, recipient, message_id)
        if key in self._delivered:
            return False
        self._delivered[key] = processed_at
        return True

    def append_event(self, session_id: str, event_payload: dict[str, Any]) -> None:
        self._session_events.setdefault(session_id, deque()).append(dict(event_payload))

    def get_session_events(self, session_id: str, *, limit: int) -> list[dict[str, Any]]:
        events = list(self._session_events.get(session_id, ()))
        if limit <= 0:
            return []
        return [dict(item) for item in events[-limit:]]

    def get_balanced_session_events(
        self,
        session_id: str,
        *,
        limit: int,
        protected_limit: int,
        noise_event_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        # Last `limit` events, plus enough older non-noise events to guarantee
        # `protected_limit` of them survive a wait/heartbeat flood of any size.
        events = list(self._session_events.get(session_id, ()))
        if limit <= 0:
            return []
        noise = set(noise_event_types)
        keep = set(range(max(0, len(events) - limit), len(events)))
        remaining = protected_limit - sum(
            1 for index in keep if str(events[index].get("event")) not in noise
        )
        for index in range(len(events) - 1, -1, -1):
            if remaining <= 0:
                break
            if index in keep or str(events[index].get("event")) in noise:
                continue
            keep.add(index)
            remaining -= 1
        return [dict(events[index]) for index in sorted(keep)]

    def count_session_events(self, session_id: str) -> int:
        return len(self._session_events.get(session_id, ()))

    def prune_noise_events_older_than(
        self, cutoff: str, *, noise_event_types: tuple[str, ...]
    ) -> int:
        # Persistent sessions never get deleted, so their wait/heartbeat spam
        # must be trimmed by retention. Protected (non-noise) events stay.
        noise = set(noise_event_types)
        removed = 0
        for session_id, events in self._session_events.items():
            kept = deque(
                item
                for item in events
                if not (str(item.get("event")) in noise and str(item.get("ts") or "") < cutoff)
            )
            removed += len(events) - len(kept)
            self._session_events[session_id] = kept
        return removed

    def last_session_event_ts(self, session_id: str) -> str | None:
        events = self._session_events.get(session_id)
        if not events:
            return None
        return events[-1].get("ts")

    def put_notice(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        notice: dict[str, Any],
    ) -> None:
        self._member_notices[(session_id, agent_name, member_token)] = dict(notice)

    def get_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None:
        notice = self._member_notices.get((session_id, agent_name, member_token))
        return dict(notice) if notice is not None else None

    def clear_notice(self, *, session_id: str, agent_name: str, member_token: str) -> None:
        self._member_notices.pop((session_id, agent_name, member_token), None)

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]:
        from datetime import datetime, timezone
        from acp.hub.coordination_state import heartbeat_age_seconds

        now = datetime.now(timezone.utc)
        removed: list[str] = []
        for session_id, session in list(self._sessions.items()):
            if session.lifecycle_mode == SESSION_LIFECYCLE_PERSISTENT:
                continue
            if not session.members:
                self.delete_session(session_id)
                removed.append(session_id)
                continue
            all_stale = True
            for member in session.members.values():
                age = heartbeat_age_seconds(member.last_seen_at, now=now)
                if age is None or age < stale_after_seconds:
                    all_stale = False
                    break
            if all_stale:
                self.delete_session(session_id)
                removed.append(session_id)
        return removed

    def prune_idempotency_older_than(self, cutoff: str) -> int:
        # Drop dedup entries processed before the cutoff so a long-lived session's
        # ledger cannot grow without bound (mirrors SqliteCoordinationStore).
        stale = [key for key, processed_at in self._delivered.items() if str(processed_at) < cutoff]
        for key in stale:
            del self._delivered[key]
        return len(stale)

    def _clone_session(self, session: CoordinationSession | None) -> CoordinationSession | None:
        if session is None:
            return None
        return CoordinationSession(
            session_id=session.session_id,
            join_code=session.join_code,
            created_by=session.created_by,
            created_at=session.created_at,
            title=session.title,
            project=session.project,
            lifecycle_mode=session.lifecycle_mode,
            members={
                member.agent_name: SessionMember(
                    agent_name=member.agent_name,
                    role=member.role,
                    member_token=member.member_token,
                    capabilities=tuple(member.capabilities),
                    delivery_mode=member.delivery_mode,
                    provider=member.provider,
                    workspace_path=member.workspace_path,
                    status=member.status,
                    status_text=member.status_text,
                    joined_at=member.joined_at,
                    last_seen_at=member.last_seen_at,
                    last_message_at=member.last_message_at,
                    last_action=member.last_action,
                    current_task=member.current_task,
                    current_task_from=member.current_task_from,
                    current_task_at=member.current_task_at,
                    current_run=_clone_run_payload(member.current_run),
                    last_run=_clone_run_payload(member.last_run),
                )
                for member in session.members.values()
            },
        )


@dataclass
class SqliteCoordinationStore:
    sqlite_path: Path | str

    def __post_init__(self) -> None:
        self._db_path = Path(self.sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # A single persistent connection per store instance so the WAL +
        # busy_timeout PRAGMAs run once (see sqlite_support.connect) instead of
        # on every query. check_same_thread=False + _lock lets us serialize all
        # access safely even if the instance is touched from more than one
        # thread; in practice every caller runs on the asyncio event loop and
        # SessionCoordinationService already wraps calls in an asyncio.Lock.
        # RLock (not Lock) because a few methods (cleanup_stale_sessions) call
        # other methods (delete_session) that re-enter the connection guard on
        # the same thread; a plain Lock would self-deadlock there.
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(
                self._db_path, row_factory=True, check_same_thread=False
            )
        return self._conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            yield self._get_connection()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __del__(self) -> None:
        # Best-effort cleanup so a store that is dropped without an explicit
        # close() (e.g. per-test instances on tmp_path) does not leave the
        # sqlite file handle open, which would block Windows temp cleanup.
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def create_session(self, session: CoordinationSession) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO coordination_sessions(
                    session_id, join_code, created_by, created_at, title, project, lifecycle_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.join_code,
                    session.created_by,
                    session.created_at,
                    session.title,
                    session.project,
                    session.lifecycle_mode,
                ),
            )
            for member in session.members.values():
                self._upsert_member(conn, session.session_id, member)
            conn.commit()

    def get_session(self, session_id: str) -> CoordinationSession | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project, lifecycle_mode
                FROM coordination_sessions
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_session(conn, row)

    def get_session_by_join_code(self, join_code: str) -> CoordinationSession | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project, lifecycle_mode
                FROM coordination_sessions
                WHERE join_code = ?
                LIMIT 1
                """,
                (join_code,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_session(conn, row)

    def list_sessions(self) -> list[CoordinationSession]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project, lifecycle_mode
                FROM coordination_sessions
                ORDER BY created_at ASC, session_id ASC
                """
            ).fetchall()
            session_ids = [str(row["session_id"]) for row in rows]
            members_by_session = self._load_members_for_sessions(conn, session_ids)
            return [
                CoordinationSession(
                    session_id=str(row["session_id"]),
                    join_code=str(row["join_code"]),
                    created_by=str(row["created_by"]),
                    created_at=str(row["created_at"]),
                    title=str(row["title"]) if row["title"] is not None else None,
                    project=str(row["project"]) if row["project"] is not None else None,
                    lifecycle_mode=str(row["lifecycle_mode"]),
                    members=members_by_session.get(str(row["session_id"]), {}),
                )
                for row in rows
            ]

    def is_agent_attached(self, agent_name: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM coordination_members
                WHERE agent_name = ?
                LIMIT 1
                """,
                (agent_name,),
            ).fetchone()
            return row is not None

    def add_member(self, session_id: str, member: SessionMember) -> None:
        with self._connection() as conn:
            self._upsert_member(conn, session_id, member)
            conn.commit()

    def update_member(self, session_id: str, member: SessionMember) -> None:
        with self._connection() as conn:
            self._upsert_member(conn, session_id, member)
            conn.commit()

    def remove_member(self, session_id: str, agent_name: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM coordination_pending_messages WHERE session_id = ? AND recipient_agent_name = ?",
                (session_id, agent_name),
            )
            conn.execute(
                "DELETE FROM coordination_members WHERE session_id = ? AND agent_name = ?",
                (session_id, agent_name),
            )
            conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM coordination_pending_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_members WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_member_notices WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def enqueue_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        priority_rank: int,
        sort_ts: str,
        message: dict[str, Any],
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO coordination_pending_messages(
                    queue_id,
                    session_id,
                    recipient_agent_name,
                    priority_rank,
                    sort_ts,
                    message_id,
                    payload_json,
                    enqueued_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    session_id,
                    recipient_agent_name,
                    priority_rank,
                    sort_ts,
                    str(message.get("id")),
                    json.dumps(message, sort_keys=True, separators=(",", ":")),
                    str(message.get("ts") or sort_ts),
                ),
            )
            conn.commit()

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str, action: str | None = None) -> dict[str, Any] | None:
        with self._connection() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
            action_clause = "" if action is None else " AND UPPER(json_extract(payload_json, '$.action')) = ?"
            params: tuple[Any, ...] = (session_id, recipient_agent_name, now) if action is None else (session_id, recipient_agent_name, now, action)
            row = conn.execute(
                f"""
                SELECT queue_id, payload_json
                FROM coordination_pending_messages
                WHERE session_id = ?
                  AND recipient_agent_name = ?
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                  {action_clause}
                ORDER BY priority_rank ASC, sort_ts ASC, queue_seq ASC
                LIMIT 1
                """,
                params,
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "DELETE FROM coordination_pending_messages WHERE queue_id = ?",
                (str(row["queue_id"]),),
            )
            conn.commit()
            payload = json.loads(str(row["payload_json"]))
            return payload if isinstance(payload, dict) else None

    def claim_next_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        receipt_handle: str,
        leased_until: str,
        now: str,
        action: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                action_clause = "" if action is None else " AND UPPER(json_extract(payload_json, '$.action')) = ?"
                params: tuple[Any, ...] = (session_id, recipient_agent_name, now) if action is None else (session_id, recipient_agent_name, now, action)
                row = conn.execute(
                    f"""
                    SELECT queue_id, payload_json
                    FROM coordination_pending_messages
                    WHERE session_id = ?
                      AND recipient_agent_name = ?
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                      {action_clause}
                    ORDER BY priority_rank ASC, sort_ts ASC, queue_seq ASC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                conn.execute(
                    """
                    UPDATE coordination_pending_messages
                    SET receipt_handle = ?, lease_expires_at = ?
                    WHERE queue_id = ?
                    """,
                    (receipt_handle, leased_until, str(row["queue_id"])),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            payload = json.loads(str(row["payload_json"]))
            return payload if isinstance(payload, dict) else None

    def acknowledge_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        message_id: str,
        receipt_handle: str,
        now: str,
    ) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM coordination_pending_messages
                WHERE session_id = ?
                  AND recipient_agent_name = ?
                  AND message_id = ?
                  AND receipt_handle = ?
                  AND lease_expires_at > ?
                """,
                (session_id, recipient_agent_name, message_id, receipt_handle, now),
            )
            conn.commit()
            return int(cursor.rowcount or 0) == 1

    def pending_count(self, *, session_id: str, agent_name: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM coordination_pending_messages
                WHERE session_id = ? AND recipient_agent_name = ?
                """,
                (session_id, agent_name),
            ).fetchone()
            return int(row[0]) if row else 0

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT recipient_agent_name, COUNT(*)
                FROM coordination_pending_messages
                WHERE session_id = ?
                GROUP BY recipient_agent_name
                """,
                (session_id,),
            ).fetchall()
            return {str(row[0]): int(row[1]) for row in rows}

    def pending_counts_for_sessions(self, session_ids: list[str]) -> dict[str, dict[str, int]]:
        if not session_ids:
            return {}
        with self._connection() as conn:
            placeholders = ",".join("?" * len(session_ids))
            rows = conn.execute(
                f"""
                SELECT session_id, recipient_agent_name, COUNT(*)
                FROM coordination_pending_messages
                WHERE session_id IN ({placeholders})
                GROUP BY session_id, recipient_agent_name
                """,
                tuple(session_ids),
            ).fetchall()
            counts: dict[str, dict[str, int]] = {}
            for row in rows:
                counts.setdefault(str(row[0]), {})[str(row[1])] = int(row[2])
            return counts

    def clear_pending(self, *, session_id: str, agent_name: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM coordination_pending_messages WHERE session_id = ? AND recipient_agent_name = ?",
                (session_id, agent_name),
            )
            conn.commit()

    def reset_session_messages(self, *, session_id: str) -> dict[str, int]:
        with self._connection() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM coordination_pending_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            events = conn.execute(
                """
                SELECT COUNT(*) FROM coordination_events
                WHERE session_id = ?
                  AND event_type IN ('MESSAGE_SENT', 'MESSAGE_DELIVERED', 'MESSAGE_ACKNOWLEDGED')
                """,
                (session_id,),
            ).fetchone()
            deliveries = conn.execute(
                "SELECT COUNT(*) FROM message_idempotency WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            conn.execute("DELETE FROM coordination_pending_messages WHERE session_id = ?", (session_id,))
            conn.execute(
                """
                DELETE FROM coordination_events
                WHERE session_id = ?
                  AND event_type IN ('MESSAGE_SENT', 'MESSAGE_DELIVERED', 'MESSAGE_ACKNOWLEDGED')
                """,
                (session_id,),
            )
            conn.execute("DELETE FROM message_idempotency WHERE session_id = ?", (session_id,))
            conn.commit()
        return {
            "cleared_pending_messages": int(pending[0]) if pending else 0,
            "cleared_message_events": int(events[0]) if events else 0,
            "cleared_delivery_ids": int(deliveries[0]) if deliveries else 0,
        }

    def record_delivery_if_new(
        self,
        *,
        session_id: str,
        recipient: str,
        message_id: str,
        processed_at: str,
    ) -> bool:
        with self._connection() as conn:
            is_new = record_if_new(
                conn,
                session_id=session_id,
                recipient=recipient,
                message_id=message_id,
                processed_at=processed_at,
            )
            conn.commit()
            return is_new

    def append_event(self, session_id: str, event_payload: dict[str, Any]) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO coordination_events(event_id, session_id, created_at, event_type, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(event_payload.get("event_id")),
                    session_id,
                    str(event_payload.get("ts")),
                    str(event_payload.get("event")),
                    json.dumps(event_payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            conn.commit()

    def get_session_events(self, session_id: str, *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM coordination_events
                WHERE session_id = ?
                ORDER BY event_seq DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
            payloads: list[dict[str, Any]] = []
            for row in reversed(rows):
                payload = json.loads(str(row["payload_json"]))
                if isinstance(payload, dict):
                    payloads.append(payload)
            return payloads

    def get_balanced_session_events(
        self,
        session_id: str,
        *,
        limit: int,
        protected_limit: int,
        noise_event_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        # Last `limit` events, plus enough older non-noise events to guarantee
        # `protected_limit` of them survive a wait/heartbeat flood of any size.
        if limit <= 0:
            return []
        with self._connection() as conn:
            recent = conn.execute(
                """
                SELECT event_seq, event_type, payload_json
                FROM coordination_events
                WHERE session_id = ?
                ORDER BY event_seq DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
            rows_by_seq: dict[int, str] = {int(row["event_seq"]): str(row["payload_json"]) for row in recent}
            noise = set(noise_event_types)
            missing = protected_limit - sum(1 for row in recent if str(row["event_type"]) not in noise)
            if missing > 0 and noise_event_types:
                min_seq = min(rows_by_seq) if rows_by_seq else 0
                placeholders = ",".join("?" for _ in noise_event_types)
                older = conn.execute(
                    f"""
                    SELECT event_seq, payload_json
                    FROM coordination_events
                    WHERE session_id = ? AND event_seq < ? AND event_type NOT IN ({placeholders})
                    ORDER BY event_seq DESC
                    LIMIT ?
                    """,
                    (session_id, min_seq, *noise_event_types, int(missing)),
                ).fetchall()
                for row in older:
                    rows_by_seq[int(row["event_seq"])] = str(row["payload_json"])
            payloads: list[dict[str, Any]] = []
            for seq in sorted(rows_by_seq):
                payload = json.loads(rows_by_seq[seq])
                if isinstance(payload, dict):
                    payloads.append(payload)
            return payloads

    def prune_noise_events_older_than(
        self, cutoff: str, *, noise_event_types: tuple[str, ...]
    ) -> int:
        # Persistent sessions never get deleted, so their wait/heartbeat spam
        # must be trimmed by retention. Protected (non-noise) events stay.
        if not noise_event_types:
            return 0
        placeholders = ",".join("?" for _ in noise_event_types)
        with self._connection() as conn:
            cursor = conn.execute(
                f"""
                DELETE FROM coordination_events
                WHERE event_type IN ({placeholders}) AND created_at < ?
                """,
                (*noise_event_types, cutoff),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def count_session_events(self, session_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM coordination_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0

    def last_session_event_ts(self, session_id: str) -> str | None:
        with self._connection() as conn:
            # created_at is stored as the event payload's "ts" (see append_event),
            # so we can read it directly without decoding payload_json.
            row = conn.execute(
                """
                SELECT created_at
                FROM coordination_events
                WHERE session_id = ?
                ORDER BY event_seq DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return str(row["created_at"]) if row is not None else None

    def put_notice(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        notice: dict[str, Any],
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO coordination_member_notices(
                    session_id,
                    agent_name,
                    member_token,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    agent_name,
                    member_token,
                    json.dumps(notice, sort_keys=True, separators=(",", ":")),
                    str(notice.get("ts")),
                ),
            )
            conn.commit()

    def get_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM coordination_member_notices
                WHERE session_id = ? AND agent_name = ? AND member_token = ?
                LIMIT 1
                """,
                (session_id, agent_name, member_token),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(str(row["payload_json"]))
            return payload if isinstance(payload, dict) else None

    def clear_notice(self, *, session_id: str, agent_name: str, member_token: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                DELETE FROM coordination_member_notices
                WHERE session_id = ? AND agent_name = ? AND member_token = ?
                """,
                (session_id, agent_name, member_token),
            )
            conn.commit()

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]:
        from datetime import datetime, timezone
        from acp.hub.coordination_state import heartbeat_age_seconds

        now = datetime.now(timezone.utc)
        removed: list[str] = []
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT session_id, lifecycle_mode FROM coordination_sessions"
            ).fetchall()
            for row in rows:
                session_id = str(row["session_id"])
                if str(row["lifecycle_mode"]) == SESSION_LIFECYCLE_PERSISTENT:
                    continue
                members = self._load_members(conn, session_id)
                if not members:
                    self.delete_session(session_id)
                    removed.append(session_id)
                    continue
                all_stale = True
                for member in members.values():
                    age = heartbeat_age_seconds(member.last_seen_at, now=now)
                    if age is None or age < stale_after_seconds:
                        all_stale = False
                        break
                if all_stale:
                    self.delete_session(session_id)
                    removed.append(session_id)
        return removed

    def prune_idempotency_older_than(self, cutoff: str) -> int:
        with self._connection() as conn:
            deleted = prune_older_than(conn, cutoff=cutoff)
            conn.commit()
            return deleted

    def _row_to_session(self, conn: sqlite3.Connection, row: sqlite3.Row) -> CoordinationSession:
        return CoordinationSession(
            session_id=str(row["session_id"]),
            join_code=str(row["join_code"]),
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
            title=str(row["title"]) if row["title"] is not None else None,
            project=str(row["project"]) if row["project"] is not None else None,
            lifecycle_mode=str(row["lifecycle_mode"]),
            members=self._load_members(conn, str(row["session_id"])),
        )

    def _load_members(self, conn: sqlite3.Connection, session_id: str) -> dict[str, SessionMember]:
        rows = conn.execute(
            """
            SELECT
                agent_name,
                role,
                member_token,
                delivery_mode,
                provider,
                workspace_path,
                status,
                status_text,
                joined_at,
                last_seen_at,
                last_message_at,
                last_action,
                current_task,
                current_task_from,
                current_task_at,
                capabilities_json,
                current_run_json,
                last_run_json
            FROM coordination_members
            WHERE session_id = ?
            ORDER BY agent_name ASC
            """,
            (session_id,),
        ).fetchall()
        members: dict[str, SessionMember] = {}
        for row in rows:
            member = _member_from_row(row)
            members[member.agent_name] = member
        return members

    def _load_members_for_sessions(
        self, conn: sqlite3.Connection, session_ids: list[str]
    ) -> dict[str, dict[str, SessionMember]]:
        members_by_session: dict[str, dict[str, SessionMember]] = {}
        if not session_ids:
            return members_by_session
        placeholders = ",".join("?" * len(session_ids))
        rows = conn.execute(
            f"""
            SELECT
                session_id,
                agent_name,
                role,
                member_token,
                delivery_mode,
                provider,
                workspace_path,
                status,
                status_text,
                joined_at,
                last_seen_at,
                last_message_at,
                last_action,
                current_task,
                current_task_from,
                current_task_at,
                capabilities_json,
                current_run_json,
                last_run_json
            FROM coordination_members
            WHERE session_id IN ({placeholders})
            ORDER BY session_id ASC, agent_name ASC
            """,
            tuple(session_ids),
        ).fetchall()
        for row in rows:
            member = _member_from_row(row)
            members_by_session.setdefault(str(row["session_id"]), {})[member.agent_name] = member
        return members_by_session

    def _upsert_member(self, conn: sqlite3.Connection, session_id: str, member: SessionMember) -> None:
        conn.execute(
            """
            INSERT INTO coordination_members(
                session_id,
                agent_name,
                member_token,
                role,
                delivery_mode,
                provider,
                workspace_path,
                status,
                status_text,
                joined_at,
                last_seen_at,
                last_message_at,
                last_action,
                current_task,
                current_task_from,
                current_task_at,
                capabilities_json,
                current_run_json,
                last_run_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, agent_name) DO UPDATE SET
                member_token = excluded.member_token,
                role = excluded.role,
                delivery_mode = excluded.delivery_mode,
                provider = excluded.provider,
                workspace_path = excluded.workspace_path,
                status = excluded.status,
                status_text = excluded.status_text,
                joined_at = excluded.joined_at,
                last_seen_at = excluded.last_seen_at,
                last_message_at = excluded.last_message_at,
                last_action = excluded.last_action,
                current_task = excluded.current_task,
                current_task_from = excluded.current_task_from,
                current_task_at = excluded.current_task_at,
                capabilities_json = excluded.capabilities_json,
                current_run_json = excluded.current_run_json,
                last_run_json = excluded.last_run_json
            """,
            (
                session_id,
                member.agent_name,
                member.member_token,
                member.role,
                member.delivery_mode,
                member.provider,
                member.workspace_path,
                member.status,
                member.status_text,
                member.joined_at,
                member.last_seen_at,
                member.last_message_at,
                member.last_action,
                member.current_task,
                member.current_task_from,
                member.current_task_at,
                _encode_capabilities(member.capabilities),
                json.dumps(member.current_run, sort_keys=True, separators=(",", ":"))
                if isinstance(member.current_run, dict)
                else None,
                json.dumps(member.last_run, sort_keys=True, separators=(",", ":"))
                if isinstance(member.last_run, dict)
                else None,
            ),
        )
