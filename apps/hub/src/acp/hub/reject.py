"""Central reject-and-trace flow for malformed inbound traffic."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from acp.hub.trace import emit_trace_drop
from acp.protocol.errors import ProtocolValidationError, build_error
from acp.protocol.models import AGENT_NAME_PATTERN, ErrorEnvelope

_SAFE_NAME = re.compile(AGENT_NAME_PATTERN)
_SAFE_DETAIL_KEYS = {"max_bytes", "actual_bytes", "limit_bytes"}
_HUB_NAME = "hub"
_UNKNOWN_RECIPIENT = "unknown"


def _normalize_recipient(sender_name: str | None, session_id: str) -> str:
    if sender_name and _SAFE_NAME.fullmatch(sender_name):
        return sender_name

    if _SAFE_NAME.fullmatch(session_id):
        return session_id

    compact = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._-")
    if compact and _SAFE_NAME.fullmatch(compact):
        return compact[:64]
    return _UNKNOWN_RECIPIENT


def _parse_raw_message(raw_message: Any) -> Mapping[str, Any] | None:
    if isinstance(raw_message, Mapping):
        return raw_message
    if not isinstance(raw_message, str):
        return None
    try:
        parsed = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None


def _extract_in_reply_to(raw_message: Any) -> UUID | None:
    parsed = _parse_raw_message(raw_message)
    if parsed is None:
        return None
    inbound_id = parsed.get("id")
    if not isinstance(inbound_id, str):
        return None
    try:
        return UUID(inbound_id)
    except ValueError:
        return None


def _sanitize_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}

    sanitized: dict[str, Any] = {}
    for key in _SAFE_DETAIL_KEYS:
        value = details.get(key)
        if isinstance(value, (int, float)):
            sanitized[key] = value
    return sanitized


def build_safe_error_envelope(
    reason: ProtocolValidationError,
    *,
    recipient: str,
    raw_message: Any,
) -> dict[str, Any]:
    envelope = ErrorEnvelope(
        id=uuid4(),
        ts=datetime.now(timezone.utc),
        from_=_HUB_NAME,
        to=recipient,
        payload=reason.message,
        code=reason.code,
        in_reply_to=_extract_in_reply_to(raw_message),
    ).model_dump(by_alias=True, mode="json")

    if reason.field:
        envelope["field"] = reason.field

    details = _sanitize_details(reason.details)
    if details:
        envelope["details"] = details

    return envelope


async def _send_error(websocket: Any, envelope: dict[str, Any]) -> None:
    if hasattr(websocket, "send_json"):
        await websocket.send_json(envelope)
        return

    if hasattr(websocket, "send_text"):
        await websocket.send_text(json.dumps(envelope))
        return

    raise TypeError("websocket must implement send_json() or send_text()")


async def send_runtime_error(
    *,
    websocket: Any,
    code: str,
    session_id: str,
    raw_message: Any,
    sender_name: str | None = None,
    field: str | None = None,
    message: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    recipient = _normalize_recipient(sender_name, session_id)
    envelope = build_safe_error_envelope(
        build_error(
            code,
            field=field,
            message=message,
            details=dict(details) if details else None,
        ),
        recipient=recipient,
        raw_message=raw_message,
    )
    await _send_error(websocket, envelope)
    return envelope


async def reject_and_trace(
    *,
    websocket: Any,
    reason: ProtocolValidationError,
    trace_sink: Any,
    session_id: str,
    raw_message: Any,
    sender_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    recipient = _normalize_recipient(sender_name, session_id)
    envelope = build_safe_error_envelope(reason, recipient=recipient, raw_message=raw_message)
    await _send_error(websocket, envelope)

    trace_event = emit_trace_drop(
        trace_sink,
        reason=reason,
        session_id=session_id,
        raw_message=raw_message,
    )
    return envelope, trace_event
