"""Shared lifecycle journaling helpers for HTTP and WS ingress paths."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from acp.hub.event_store import EventStore
from acp.protocol.models import AGENT_NAME_PATTERN

EVENT_RECEIVED = "received"
EVENT_ROUTED = "routed"
EVENT_REJECTED = "rejected"
EVENT_DELIVERY_FAILED = "delivery_failed"

INGRESS_HTTP = "http"
INGRESS_WS = "ws"

_SAFE_NAME = re.compile(AGENT_NAME_PATTERN)
_SAFE_ACTION = re.compile(r"^[A-Z_]{1,24}$")
_SAFE_INGRESS = {INGRESS_HTTP, INGRESS_WS}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _safe_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if _SAFE_NAME.fullmatch(value) is None:
        return None
    return value


def _safe_action(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if _SAFE_ACTION.fullmatch(value) is None:
        return None
    return value


def _safe_reason_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if len(cleaned) > 64:
        cleaned = cleaned[:64]
    return re.sub(r"[^A-Z0-9_]+", "_", cleaned)


def _event_id(*, msg_id: str | None, event_type: str, reason_code: str | None) -> str:
    if msg_id is None:
        return str(uuid4())
    parts = [msg_id, event_type]
    if reason_code:
        parts.append(reason_code.lower())
    return ":".join(parts)


def _base_payload(
    *,
    event_type: str,
    ingress: str,
    raw_message: Mapping[str, Any] | None,
    reason_code: str | None,
    sender_fallback: str | None,
) -> dict[str, Any]:
    if ingress not in _SAFE_INGRESS:
        ingress = INGRESS_HTTP

    raw = raw_message or {}
    msg_id = _safe_uuid(raw.get("id"))
    reason = _safe_reason_code(reason_code)

    payload: dict[str, Any] = {
        "event_id": _event_id(msg_id=msg_id, event_type=event_type, reason_code=reason),
        "created_at": _utc_now_iso(),
        "msg_id": msg_id,
        "thread_id": _safe_uuid(raw.get("thread_id")),
        "from": _safe_name(raw.get("from")) or _safe_name(sender_fallback),
        "to": _safe_name(raw.get("to")),
        "action": _safe_action(raw.get("action")),
        "ingress": ingress,
        "reason_code": reason,
    }
    # Secret-safe allowlist only.
    return {key: value for key, value in payload.items() if value is not None}


def append_received(
    *,
    event_store: EventStore,
    ingress: str,
    message: Mapping[str, Any],
    sender_fallback: str | None = None,
) -> None:
    payload = _base_payload(
        event_type=EVENT_RECEIVED,
        ingress=ingress,
        raw_message=message,
        reason_code=None,
        sender_fallback=sender_fallback,
    )
    event_store.append(event_type=EVENT_RECEIVED, payload=payload)


def append_routed(
    *,
    event_store: EventStore,
    ingress: str,
    message: Mapping[str, Any],
    sender_fallback: str | None = None,
) -> None:
    payload = _base_payload(
        event_type=EVENT_ROUTED,
        ingress=ingress,
        raw_message=message,
        reason_code=None,
        sender_fallback=sender_fallback,
    )
    event_store.append(event_type=EVENT_ROUTED, payload=payload)


def append_rejected(
    *,
    event_store: EventStore,
    ingress: str,
    reason_code: str,
    message: Mapping[str, Any] | None = None,
    sender_fallback: str | None = None,
) -> None:
    payload = _base_payload(
        event_type=EVENT_REJECTED,
        ingress=ingress,
        raw_message=message,
        reason_code=reason_code,
        sender_fallback=sender_fallback,
    )
    event_store.append(event_type=EVENT_REJECTED, payload=payload)


def append_delivery_failed(
    *,
    event_store: EventStore,
    ingress: str,
    reason_code: str,
    message: Mapping[str, Any],
    sender_fallback: str | None = None,
) -> None:
    payload = _base_payload(
        event_type=EVENT_DELIVERY_FAILED,
        ingress=ingress,
        raw_message=message,
        reason_code=reason_code,
        sender_fallback=sender_fallback,
    )
    event_store.append(event_type=EVENT_DELIVERY_FAILED, payload=payload)
