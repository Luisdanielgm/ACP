"""Event store ports and in-memory defaults for phase-8 replay queries."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Protocol
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


ReplayOrder = Literal["asc", "desc"]
_TERMINAL_EVENT_TYPES = {"routed", "rejected", "delivery_failed"}


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    event_type: str
    ts: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReplayFilters:
    from_ts: str | None = None
    to_ts: str | None = None
    actor: str | None = None
    event_type: str | None = None
    message_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class ReplayCursor:
    order: ReplayOrder
    created_at: str
    event_id: str
    filters_hash: str


@dataclass(frozen=True)
class ReplayPage:
    events: list[StoredEvent]
    next_cursor: str | None
    order: ReplayOrder
    limit: int


@dataclass(frozen=True)
class ReplayTimeline:
    message_id: str
    timeline_status: Literal["complete", "partial"]
    events: list[StoredEvent]


def replay_filters_hash(filters: ReplayFilters) -> str:
    serialized = json.dumps(
        {
            "from_ts": filters.from_ts,
            "to_ts": filters.to_ts,
            "actor": filters.actor,
            "event_type": filters.event_type,
            "message_id": filters.message_id,
            "thread_id": filters.thread_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def encode_replay_cursor(cursor: ReplayCursor) -> str:
    raw = json.dumps(
        {
            "v": 1,
            "order": cursor.order,
            "created_at": cursor.created_at,
            "event_id": cursor.event_id,
            "filters_hash": cursor.filters_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def decode_replay_cursor(
    value: str,
    *,
    expected_order: ReplayOrder,
    expected_filters_hash: str,
) -> ReplayCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        decoded = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parser guard
        raise ValueError("cursor is malformed") from exc

    if not isinstance(decoded, dict):
        raise ValueError("cursor is malformed")
    if decoded.get("v") != 1:
        raise ValueError("cursor version is unsupported")
    order = decoded.get("order")
    created_at = decoded.get("created_at")
    event_id = decoded.get("event_id")
    filters_hash = decoded.get("filters_hash")

    if order not in {"asc", "desc"}:
        raise ValueError("cursor order is invalid")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError("cursor created_at is invalid")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("cursor event_id is invalid")
    if not isinstance(filters_hash, str) or not filters_hash:
        raise ValueError("cursor filters_hash is invalid")
    if order != expected_order:
        raise ValueError("cursor does not match order")
    if filters_hash != expected_filters_hash:
        raise ValueError("cursor does not match filters")

    return ReplayCursor(
        order=order,
        created_at=created_at,
        event_id=event_id,
        filters_hash=filters_hash,
    )


class EventStore(Protocol):
    """Port used by hub runtime to append auditable events."""

    def append(self, *, event_type: str, payload: Mapping[str, Any]) -> None:
        ...

    def query_events(
        self,
        *,
        filters: ReplayFilters,
        order: ReplayOrder,
        limit: int,
        cursor: str | None,
    ) -> ReplayPage:
        ...

    def query_message_timeline(self, *, message_id: str) -> ReplayTimeline | None:
        ...

    def get_scopes_for_principal(self, principal_name: str) -> set[str] | None:
        ...

    def get_acl_decision(self, *, sender: str, recipient: str, action: str) -> Literal["allow", "deny"] | None:
        ...


@dataclass
class InMemoryEventStore:
    """Default event store for parity mode and test harnesses."""

    events: list[StoredEvent] = field(default_factory=list)
    principal_scopes: dict[str, set[str]] = field(default_factory=dict)
    acl_rules: list[tuple[str, str, str, bool]] = field(default_factory=list)

    def append(self, *, event_type: str, payload: Mapping[str, Any]) -> None:
        payload_copy = dict(payload)
        event_id = payload_copy.get("event_id")
        ts = payload_copy.get("created_at")
        if not isinstance(event_id, str) or not event_id:
            event_id = str(uuid4())
        if not isinstance(ts, str) or not ts:
            ts = _utc_now_iso()
        self.events.append(
            StoredEvent(
                event_id=event_id,
                event_type=event_type,
                ts=ts,
                payload=payload_copy,
            )
        )

    def count(self) -> int:
        return len(self.events)

    def snapshot(self) -> list[StoredEvent]:
        return list(self.events)

    @staticmethod
    def _event_matches_filters(event: StoredEvent, filters: ReplayFilters) -> bool:
        payload = event.payload
        if filters.from_ts is not None and event.ts < filters.from_ts:
            return False
        if filters.to_ts is not None and event.ts > filters.to_ts:
            return False
        if filters.event_type is not None and event.event_type != filters.event_type:
            return False
        if filters.message_id is not None and payload.get("msg_id") != filters.message_id:
            return False
        if filters.thread_id is not None and payload.get("thread_id") != filters.thread_id:
            return False
        if filters.actor is not None:
            from_name = payload.get("from")
            to_name = payload.get("to")
            if from_name != filters.actor and to_name != filters.actor:
                return False
        return True

    @staticmethod
    def _past_cursor_boundary(event: StoredEvent, cursor: ReplayCursor) -> bool:
        event_key = (event.ts, event.event_id)
        cursor_key = (cursor.created_at, cursor.event_id)
        if cursor.order == "desc":
            return event_key < cursor_key
        return event_key > cursor_key

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

        filters_hash = replay_filters_hash(filters)
        parsed_cursor: ReplayCursor | None = None
        if cursor is not None:
            parsed_cursor = decode_replay_cursor(
                cursor,
                expected_order=order,
                expected_filters_hash=filters_hash,
            )

        filtered = [event for event in self.snapshot() if self._event_matches_filters(event, filters)]
        filtered.sort(key=lambda event: (event.ts, event.event_id), reverse=order == "desc")
        if parsed_cursor is not None:
            filtered = [event for event in filtered if self._past_cursor_boundary(event, parsed_cursor)]

        page_events = filtered[:limit]
        has_more = len(filtered) > limit
        next_cursor: str | None = None
        if has_more and page_events:
            last = page_events[-1]
            next_cursor = encode_replay_cursor(
                ReplayCursor(
                    order=order,
                    created_at=last.ts,
                    event_id=last.event_id,
                    filters_hash=filters_hash,
                )
            )

        return ReplayPage(events=page_events, next_cursor=next_cursor, order=order, limit=limit)

    def query_message_timeline(self, *, message_id: str) -> ReplayTimeline | None:
        events = [event for event in self.snapshot() if event.payload.get("msg_id") == message_id]
        if not events:
            return None
        events.sort(key=lambda event: (event.ts, event.event_id))
        event_types = {event.event_type for event in events}
        status: Literal["complete", "partial"] = (
            "complete"
            if ("received" in event_types and bool(event_types.intersection(_TERMINAL_EVENT_TYPES)))
            else "partial"
        )
        return ReplayTimeline(message_id=message_id, timeline_status=status, events=events)

    def get_scopes_for_principal(self, principal_name: str) -> set[str] | None:
        scopes = self.principal_scopes.get(principal_name)
        if scopes is None:
            return None
        return {str(scope).strip() for scope in scopes if str(scope).strip()}

    def get_acl_decision(self, *, sender: str, recipient: str, action: str) -> Literal["allow", "deny"] | None:
        matching = [
            allow
            for rule_sender, rule_recipient, rule_action, allow in self.acl_rules
            if rule_sender == sender and rule_recipient == recipient and rule_action == action
        ]
        if not matching:
            return None
        if any(allow is False for allow in matching):
            return "deny"
        if any(allow is True for allow in matching):
            return "allow"
        return None
