"""Sqlite-backed durable EventStore adapter."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import uuid4

from acp.hub.event_store import (
    ReplayCursor,
    ReplayFilters,
    ReplayOrder,
    ReplayPage,
    ReplayTimeline,
    StoredEvent,
    decode_replay_cursor,
    encode_replay_cursor,
    replay_filters_hash,
)
from acp.hub.sqlite_support import connect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize_rfc3339(value: Any) -> str:
    if not isinstance(value, str):
        return _utc_now_iso()
    cleaned = value.strip()
    if not cleaned:
        return _utc_now_iso()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return _utc_now_iso()
    if parsed.tzinfo is None:
        return _utc_now_iso()
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass
class SqliteEventStore:
    sqlite_path: Path | str

    def __post_init__(self) -> None:
        self._db_path = Path(self.sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return connect(self._db_path)

    def _normalize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        payload_copy = dict(payload)
        event_id = payload_copy.get("event_id")
        created_at = payload_copy.get("created_at")

        if not isinstance(event_id, str) or not event_id:
            event_id = str(uuid4())
            payload_copy["event_id"] = event_id
        created_at = _normalize_rfc3339(created_at)
        payload_copy["created_at"] = created_at
        return payload_copy

    @staticmethod
    def _row_to_event(row: tuple[Any, Any, Any, Any]) -> StoredEvent:
        event_id, event_type, created_at, payload_json = row
        payload = json.loads(payload_json)
        return StoredEvent(
            event_id=str(event_id),
            event_type=str(event_type),
            ts=str(created_at),
            payload=payload if isinstance(payload, dict) else {},
        )

    def append(self, *, event_type: str, payload: Mapping[str, Any]) -> None:
        payload_copy = self._normalize_payload(payload)
        event_id = str(payload_copy["event_id"])
        created_at = str(payload_copy["created_at"])

        payload_json = json.dumps(payload_copy, sort_keys=True, separators=(",", ":"))

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO persisted_events(event_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, event_type, created_at, payload_json),
            )
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) FROM persisted_events").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def exists_event_id(self, event_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM persisted_events WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def snapshot(self) -> list[StoredEvent]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, created_at, payload_json
                FROM persisted_events
                ORDER BY created_at ASC, event_id ASC
                """
            ).fetchall()
        finally:
            conn.close()

        return [self._row_to_event(row) for row in rows]

    def events_for_msg(self, msg_id: str) -> list[StoredEvent]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, created_at, payload_json
                FROM persisted_events
                WHERE json_extract(payload_json, '$.msg_id') = ?
                ORDER BY created_at ASC, event_id ASC
                """,
                (msg_id,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_event(row) for row in rows]

    def event_types_for_msg(self, msg_id: str) -> list[str]:
        return [event.event_type for event in self.events_for_msg(msg_id)]

    def latest_for_msg(self, msg_id: str) -> StoredEvent | None:
        events = self.events_for_msg(msg_id)
        if not events:
            return None
        return events[-1]

    def first_for_msg(self, msg_id: str) -> StoredEvent | None:
        events = self.events_for_msg(msg_id)
        if not events:
            return None
        return events[0]

    def all_message_ids(self) -> list[str]:
        msg_ids: list[str] = []
        seen: set[str] = set()
        for event in self.snapshot():
            msg_id = event.payload.get("msg_id")
            if not isinstance(msg_id, str):
                continue
            if msg_id in seen:
                continue
            seen.add(msg_id)
            msg_ids.append(msg_id)
        return msg_ids

    def events_by_type(self, event_type: str) -> list[StoredEvent]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, created_at, payload_json
                FROM persisted_events
                WHERE event_type = ?
                ORDER BY created_at ASC, event_id ASC
                """,
                (event_type,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_event(row) for row in rows]

    def events_by_ingress(self, ingress: str) -> list[StoredEvent]:
        return [event for event in self.snapshot() if event.payload.get("ingress") == ingress]

    def rejected_with_reason(self, reason_code: str) -> list[StoredEvent]:
        return [
            event
            for event in self.events_by_type("rejected")
            if event.payload.get("reason_code") == reason_code
        ]

    def count_for_msg(self, msg_id: str) -> int:
        return len(self.events_for_msg(msg_id))

    def has_lifecycle_pair(self, msg_id: str) -> bool:
        event_types = set(self.event_types_for_msg(msg_id))
        return "received" in event_types and (
            "routed" in event_types or "rejected" in event_types or "delivery_failed" in event_types
        )

    def clear_for_tests(self) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM persisted_events")
            conn.commit()
        finally:
            conn.close()

    def lifecycle_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for event in self.snapshot():
            summary[event.event_type] = summary.get(event.event_type, 0) + 1
        return summary

    def get_scopes_for_principal(self, principal_name: str) -> set[str] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT scopes_csv
                FROM auth_principals
                WHERE principal_name = ?
                LIMIT 1
                """,
                (principal_name,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        scopes_csv = row[0]
        if not isinstance(scopes_csv, str):
            return set()
        return {
            scope.strip()
            for scope in scopes_csv.split(",")
            if isinstance(scope, str) and scope.strip()
        }

    def get_acl_decision(self, *, sender: str, recipient: str, action: str) -> Literal["allow", "deny"] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*), MIN(allow), MAX(allow)
                FROM acl_rules
                WHERE sender = ? AND recipient = ? AND action = ?
                """,
                (sender, recipient, action),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        count, minimum, maximum = row
        if int(count) <= 0:
            return None
        # Precedence is deny > allow when conflicting rules exist.
        if int(minimum) == 0:
            return "deny"
        if int(maximum) == 1:
            return "allow"
        return None

    @staticmethod
    def _cursor_where_clause(order: ReplayOrder) -> str:
        if order == "desc":
            return (
                "("
                "created_at < :cursor_created_at "
                "OR (created_at = :cursor_created_at AND event_id < :cursor_event_id)"
                ")"
            )
        return (
            "("
            "created_at > :cursor_created_at "
            "OR (created_at = :cursor_created_at AND event_id > :cursor_event_id)"
            ")"
        )

    def query_events(
        self,
        *,
        filters: ReplayFilters,
        order: ReplayOrder,
        limit: int,
        cursor: str | None,
    ) -> ReplayPage:
        if order not in {"asc", "desc"}:
            raise ValueError("order must be asc or desc")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        params: dict[str, Any] = {
            "from_ts": filters.from_ts,
            "to_ts": filters.to_ts,
            "actor": filters.actor,
            "event_type": filters.event_type,
            "message_id": filters.message_id,
            "thread_id": filters.thread_id,
            "limit_plus_one": limit + 1,
        }
        where = [
            "(:event_type IS NULL OR event_type = :event_type)",
            "(:from_ts IS NULL OR created_at >= :from_ts)",
            "(:to_ts IS NULL OR created_at <= :to_ts)",
            "(:message_id IS NULL OR json_extract(payload_json, '$.msg_id') = :message_id)",
            "(:thread_id IS NULL OR json_extract(payload_json, '$.thread_id') = :thread_id)",
            "(:actor IS NULL OR json_extract(payload_json, '$.from') = :actor OR json_extract(payload_json, '$.to') = :actor)",
        ]

        filters_hash = replay_filters_hash(filters)
        if cursor is not None:
            parsed_cursor = decode_replay_cursor(
                cursor,
                expected_order=order,
                expected_filters_hash=filters_hash,
            )
            params["cursor_created_at"] = parsed_cursor.created_at
            params["cursor_event_id"] = parsed_cursor.event_id
            where.append(self._cursor_where_clause(order))

        direction = "DESC" if order == "desc" else "ASC"
        sql = (
            "SELECT event_id, event_type, created_at, payload_json "
            "FROM persisted_events "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY created_at {direction}, event_id {direction} "
            "LIMIT :limit_plus_one"
        )

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        events = [self._row_to_event(row) for row in page_rows]
        next_cursor: str | None = None
        if has_more and events:
            last_event = events[-1]
            next_cursor = encode_replay_cursor(
                ReplayCursor(
                    order=order,
                    created_at=last_event.ts,
                    event_id=last_event.event_id,
                    filters_hash=filters_hash,
                )
            )

        return ReplayPage(events=events, next_cursor=next_cursor, order=order, limit=limit)

    def query_message_timeline(self, *, message_id: str) -> ReplayTimeline | None:
        events = self.events_for_msg(message_id)
        if not events:
            return None
        event_types = {event.event_type for event in events}
        timeline_status = (
            "complete"
            if ("received" in event_types and bool({"routed", "rejected", "delivery_failed"} & event_types))
            else "partial"
        )
        return ReplayTimeline(
            message_id=message_id,
            timeline_status=timeline_status,
            events=events,
        )
