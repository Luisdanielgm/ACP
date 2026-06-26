"""Coordination state stores for session-oriented workflows."""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from acp.hub.coordination_state import CoordinationSession, SessionMember
from acp.hub.idempotency import record_if_new
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

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str) -> dict[str, Any] | None: ...

    def pending_count(self, *, session_id: str, agent_name: str) -> int: ...

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]: ...

    def clear_pending(self, *, session_id: str, agent_name: str) -> None: ...

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

    def put_notice(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        notice: dict[str, Any],
    ) -> None: ...

    def get_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None: ...

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]: ...


@dataclass
class InMemoryCoordinationStore:
    _sessions: dict[str, CoordinationSession] = field(default_factory=dict)
    _sessions_by_code: dict[str, str] = field(default_factory=dict)
    _agent_to_session: dict[str, str] = field(default_factory=dict)
    _pending_messages: dict[tuple[str, str], deque[dict[str, Any]]] = field(default_factory=dict)
    _session_events: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)
    _member_notices: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    _delivered: set[tuple[str, str, str]] = field(default_factory=set)

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
        self._delivered = {key for key in self._delivered if key[0] != session_id}

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

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str) -> dict[str, Any] | None:
        queue = self._pending_messages.get((session_id, recipient_agent_name))
        if not queue:
            return None
        best_index = 0
        best_key = (int(queue[0].get("_priority_rank", 0)), str(queue[0].get("_sort_ts", "")))
        for index, message in enumerate(queue):
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

    def pending_count(self, *, session_id: str, agent_name: str) -> int:
        return len(self._pending_messages.get((session_id, agent_name), ()))

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for (queued_session_id, agent_name), queue in self._pending_messages.items():
            if queued_session_id == session_id:
                counts[agent_name] = len(queue)
        return counts

    def clear_pending(self, *, session_id: str, agent_name: str) -> None:
        self._pending_messages.pop((session_id, agent_name), None)

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
        self._delivered.add(key)
        return True

    def append_event(self, session_id: str, event_payload: dict[str, Any]) -> None:
        self._session_events.setdefault(session_id, deque()).append(dict(event_payload))

    def get_session_events(self, session_id: str, *, limit: int) -> list[dict[str, Any]]:
        events = list(self._session_events.get(session_id, ()))
        if limit <= 0:
            return []
        return [dict(item) for item in events[-limit:]]

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

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]:
        from datetime import datetime, timezone
        from acp.hub.coordination_state import heartbeat_age_seconds

        now = datetime.now(timezone.utc)
        removed: list[str] = []
        for session_id, session in list(self._sessions.items()):
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

    def _connect(self) -> sqlite3.Connection:
        return connect(self._db_path, row_factory=True)

    def create_session(self, session: CoordinationSession) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO coordination_sessions(
                    session_id, join_code, created_by, created_at, title, project
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.join_code,
                    session.created_by,
                    session.created_at,
                    session.title,
                    session.project,
                ),
            )
            for member in session.members.values():
                self._upsert_member(conn, session.session_id, member)
            conn.commit()
        finally:
            conn.close()

    def get_session(self, session_id: str) -> CoordinationSession | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project
                FROM coordination_sessions
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_session(conn, row)
        finally:
            conn.close()

    def get_session_by_join_code(self, join_code: str) -> CoordinationSession | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project
                FROM coordination_sessions
                WHERE join_code = ?
                LIMIT 1
                """,
                (join_code,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_session(conn, row)
        finally:
            conn.close()

    def list_sessions(self) -> list[CoordinationSession]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, join_code, created_by, created_at, title, project
                FROM coordination_sessions
                ORDER BY created_at ASC, session_id ASC
                """
            ).fetchall()
            return [self._row_to_session(conn, row) for row in rows]
        finally:
            conn.close()

    def is_agent_attached(self, agent_name: str) -> bool:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def add_member(self, session_id: str, member: SessionMember) -> None:
        conn = self._connect()
        try:
            self._upsert_member(conn, session_id, member)
            conn.commit()
        finally:
            conn.close()

    def update_member(self, session_id: str, member: SessionMember) -> None:
        conn = self._connect()
        try:
            self._upsert_member(conn, session_id, member)
            conn.commit()
        finally:
            conn.close()

    def remove_member(self, session_id: str, agent_name: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM coordination_pending_messages WHERE session_id = ? AND recipient_agent_name = ?",
                (session_id, agent_name),
            )
            conn.execute(
                "DELETE FROM coordination_members WHERE session_id = ? AND agent_name = ?",
                (session_id, agent_name),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM coordination_pending_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_members WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_member_notices WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM coordination_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def enqueue_message(
        self,
        *,
        session_id: str,
        recipient_agent_name: str,
        priority_rank: int,
        sort_ts: str,
        message: dict[str, Any],
    ) -> None:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def dequeue_next_message(self, *, session_id: str, recipient_agent_name: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT queue_id, payload_json
                FROM coordination_pending_messages
                WHERE session_id = ? AND recipient_agent_name = ?
                ORDER BY priority_rank ASC, sort_ts ASC, queue_seq ASC
                LIMIT 1
                """,
                (session_id, recipient_agent_name),
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
        finally:
            conn.close()

    def pending_count(self, *, session_id: str, agent_name: str) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM coordination_pending_messages
                WHERE session_id = ? AND recipient_agent_name = ?
                """,
                (session_id, agent_name),
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def pending_counts_for_session(self, session_id: str) -> dict[str, int]:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def clear_pending(self, *, session_id: str, agent_name: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM coordination_pending_messages WHERE session_id = ? AND recipient_agent_name = ?",
                (session_id, agent_name),
            )
            conn.commit()
        finally:
            conn.close()

    def record_delivery_if_new(
        self,
        *,
        session_id: str,
        recipient: str,
        message_id: str,
        processed_at: str,
    ) -> bool:
        conn = self._connect()
        try:
            is_new = record_if_new(
                conn,
                session_id=session_id,
                recipient=recipient,
                message_id=message_id,
                processed_at=processed_at,
            )
            conn.commit()
            return is_new
        finally:
            conn.close()

    def append_event(self, session_id: str, event_payload: dict[str, Any]) -> None:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def get_session_events(self, session_id: str, *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def put_notice(
        self,
        *,
        session_id: str,
        agent_name: str,
        member_token: str,
        notice: dict[str, Any],
    ) -> None:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def get_notice(self, *, session_id: str, agent_name: str, member_token: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
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
        finally:
            conn.close()

    def cleanup_stale_sessions(self, *, stale_after_seconds: int) -> list[str]:
        from datetime import datetime, timezone
        from acp.hub.coordination_state import heartbeat_age_seconds

        now = datetime.now(timezone.utc)
        removed: list[str] = []
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT session_id FROM coordination_sessions"
            ).fetchall()
            for row in rows:
                session_id = str(row["session_id"])
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
        finally:
            conn.close()
        return removed

    def _row_to_session(self, conn: sqlite3.Connection, row: sqlite3.Row) -> CoordinationSession:
        return CoordinationSession(
            session_id=str(row["session_id"]),
            join_code=str(row["join_code"]),
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
            title=str(row["title"]) if row["title"] is not None else None,
            project=str(row["project"]) if row["project"] is not None else None,
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
            member = SessionMember(
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
                current_task_from=(
                    str(row["current_task_from"]) if row["current_task_from"] is not None else None
                ),
                current_task_at=str(row["current_task_at"]) if row["current_task_at"] is not None else None,
                current_run=_decode_optional_json_object(row["current_run_json"]),
                last_run=_decode_optional_json_object(row["last_run_json"]),
            )
            members[member.agent_name] = member
        return members

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
