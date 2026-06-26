"""Trace emission helpers for lifecycle and DROP metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from acp.protocol.errors import ProtocolValidationError
from acp.protocol.models import AGENT_NAME_PATTERN

_SAFE_DETAIL_KEYS = {"max_bytes", "actual_bytes", "limit_bytes"}
_SAFE_NAME = re.compile(AGENT_NAME_PATTERN)
_SAFE_ROLES = {"agent", "observer"}
_SAFE_SCOPES = {"connect", "send", "observe", "replay"}
_SAFE_DECISIONS = {"allow", "would_deny", "deny"}
_SAFE_SURFACE = re.compile(r"^[a-z0-9_]{1,32}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _coerce_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
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


def _emit(trace_sink: Any, event: dict[str, Any]) -> None:
    if trace_sink is None:
        return
    if hasattr(trace_sink, "append"):
        trace_sink.append(event)
        return
    if hasattr(trace_sink, "emit"):
        trace_sink.emit(event)
        return
    if callable(trace_sink):
        trace_sink(event)


def _sanitize_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if _SAFE_NAME.fullmatch(value) is None:
        return None
    return value


def _sanitize_role(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value not in _SAFE_ROLES:
        return None
    return value


def _sanitize_action(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) > 24:
        return None
    if re.fullmatch(r"[A-Z_]+", value) is None:
        return None
    return value


def _base_lifecycle_event(event_name: str, *, session_id: str) -> dict[str, Any]:
    return {
        "type": "TRACE",
        "event": event_name,
        "ts": _utc_now_iso(),
        "source_session": session_id,
    }


def emit_trace_connect(
    trace_sink: Any,
    *,
    session_id: str,
    role: str,
    name: str,
) -> dict[str, Any]:
    event = _base_lifecycle_event("CONNECT", session_id=session_id)
    safe_role = _sanitize_role(role)
    safe_name = _sanitize_name(name)
    if safe_role is not None:
        event["role"] = safe_role
    if safe_name is not None:
        event["name"] = safe_name
    _emit(trace_sink, event)
    return event


def emit_trace_disconnect(
    trace_sink: Any,
    *,
    session_id: str,
    role: str,
    name: str,
) -> dict[str, Any]:
    event = _base_lifecycle_event("DISCONNECT", session_id=session_id)
    safe_role = _sanitize_role(role)
    safe_name = _sanitize_name(name)
    if safe_role is not None:
        event["role"] = safe_role
    if safe_name is not None:
        event["name"] = safe_name
    _emit(trace_sink, event)
    return event


def emit_trace_drop(
    trace_sink: Any,
    *,
    reason: ProtocolValidationError,
    session_id: str,
    raw_message: Any,
) -> dict[str, Any]:
    parsed = _parse_raw_message(raw_message)

    event: dict[str, Any] = {
        "type": "TRACE",
        "event": "DROP",
        "ts": _utc_now_iso(),
        "source_session": session_id,
        "reason_code": reason.code,
    }
    if reason.field:
        event["invalid_field"] = reason.field

    if parsed is not None:
        msg_type = parsed.get("type")
        if isinstance(msg_type, str):
            event["message_type"] = msg_type

        msg_id = _coerce_uuid(parsed.get("id"))
        if msg_id is not None:
            event["msg_id"] = msg_id

        payload = parsed.get("payload")
        if isinstance(payload, str):
            event["payload_bytes"] = len(payload.encode("utf-8"))

    event.update(_sanitize_details(reason.details))
    _emit(trace_sink, event)
    return event


def emit_trace_route(
    trace_sink: Any,
    *,
    session_id: str,
    msg_id: Any,
    from_name: Any,
    to_name: Any,
    action: Any,
    thread_id: Any = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "TRACE",
        "event": "ROUTE",
        "ts": _utc_now_iso(),
        "source_session": session_id,
    }

    safe_msg_id = _coerce_uuid(msg_id)
    if safe_msg_id is not None:
        event["msg_id"] = safe_msg_id

    safe_from = _sanitize_name(from_name)
    if safe_from is not None:
        event["from"] = safe_from

    safe_to = _sanitize_name(to_name)
    if safe_to is not None:
        event["to"] = safe_to

    safe_action = _sanitize_action(action)
    if safe_action is not None:
        event["action"] = safe_action

    safe_thread_id = _coerce_uuid(thread_id)
    if safe_thread_id is not None:
        event["thread_id"] = safe_thread_id

    _emit(trace_sink, event)
    return event


def emit_trace_error(
    trace_sink: Any,
    *,
    session_id: str,
    reason_code: str,
    requested_to: Any,
    in_reply_to: Any = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "TRACE",
        "event": "ERROR",
        "ts": _utc_now_iso(),
        "source_session": session_id,
        "reason_code": reason_code,
    }

    safe_requested_to = _sanitize_name(requested_to)
    if safe_requested_to is not None:
        event["requested_to"] = safe_requested_to

    safe_in_reply_to = _coerce_uuid(in_reply_to)
    if safe_in_reply_to is not None:
        event["in_reply_to"] = safe_in_reply_to

    _emit(trace_sink, event)
    return event


def emit_trace_authz(
    trace_sink: Any,
    *,
    session_id: str,
    principal: Any,
    scope: Any,
    surface: Any,
    decision: Any,
    reason_code: Any,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "TRACE",
        "event": "AUTHZ",
        "ts": _utc_now_iso(),
        "source_session": session_id,
    }

    safe_principal = _sanitize_name(principal)
    if safe_principal is not None:
        event["principal"] = safe_principal

    if isinstance(scope, str) and scope in _SAFE_SCOPES:
        event["scope"] = scope

    if isinstance(surface, str) and _SAFE_SURFACE.fullmatch(surface) is not None:
        event["surface"] = surface

    if isinstance(decision, str) and decision in _SAFE_DECISIONS:
        event["decision"] = decision

    if isinstance(reason_code, str):
        sanitized_reason = re.sub(r"[^A-Z0-9_]+", "_", reason_code.strip().upper())
        if sanitized_reason:
            event["reason_code"] = sanitized_reason[:64]

    _emit(trace_sink, event)
    return event
