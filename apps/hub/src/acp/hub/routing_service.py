"""Shared transport-agnostic routing primitives for hub ingress adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from acp.protocol.errors import INVALID_FIELD

ROUTE_STATUS_ROUTED = "ROUTED"
ROUTE_STATUS_DESTINATION_NOT_FOUND = "DESTINATION_NOT_FOUND"
ROUTE_STATUS_DELIVERY_FAILED = "DELIVERY_FAILED"


@dataclass(frozen=True)
class RouteResult:
    """Normalized route outcome returned to websocket and HTTP adapters."""

    status: str
    destination: str | None = None
    reason_code: str | None = None
    code: str | None = None
    field: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == ROUTE_STATUS_ROUTED

    @property
    def is_missing_destination(self) -> bool:
        return self.status == ROUTE_STATUS_DESTINATION_NOT_FOUND

    @property
    def is_delivery_failed(self) -> bool:
        return self.status == ROUTE_STATUS_DELIVERY_FAILED

    def to_error_payload(self, *, in_reply_to: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "error",
            "code": self.code or INVALID_FIELD,
            "field": self.field or "to",
            "message": self.message or "destination agent is unavailable.",
        }
        if in_reply_to is not None:
            payload["in_reply_to"] = in_reply_to
        return payload


async def _send_json(websocket: Any, payload: Mapping[str, Any]) -> None:
    if hasattr(websocket, "send_json"):
        await websocket.send_json(dict(payload))
        return
    if hasattr(websocket, "send_text"):
        import json

        await websocket.send_text(json.dumps(dict(payload)))
        return
    raise TypeError("destination websocket must implement send_json() or send_text()")


def _destination_from_payload(payload: Mapping[str, Any]) -> str | None:
    destination = payload.get("to")
    if not isinstance(destination, str):
        return None
    return destination


def _missing_destination_result(destination: str | None) -> RouteResult:
    return RouteResult(
        status=ROUTE_STATUS_DESTINATION_NOT_FOUND,
        destination=destination,
        reason_code="DESTINATION_NOT_FOUND",
        code=INVALID_FIELD,
        field="to",
        message="destination agent is not connected.",
    )


def _delivery_failed_result(destination: str) -> RouteResult:
    return RouteResult(
        status=ROUTE_STATUS_DELIVERY_FAILED,
        destination=destination,
        reason_code="DESTINATION_DELIVERY_FAILED",
        code=INVALID_FIELD,
        field="to",
        message="destination agent is temporarily unavailable.",
    )


def _routed_result(destination: str) -> RouteResult:
    return RouteResult(
        status=ROUTE_STATUS_ROUTED,
        destination=destination,
    )


async def route_validated_msg(
    *,
    payload: Mapping[str, Any],
    active_agents: MutableMapping[str, Any],
) -> RouteResult:
    """Route a validated MSG payload to its destination if available.

    This function is intentionally transport-agnostic: websocket ingress and
    HTTP `/send` call the same routing core so destination behavior cannot drift.
    Sender identity checks remain adapter-specific because websocket sessions
    have bound identities while HTTP senders are explicit payload fields.
    """

    destination = _destination_from_payload(payload)
    if destination is None:
        return _missing_destination_result(destination=None)

    destination_socket = active_agents.get(destination)
    if destination_socket is None:
        return _missing_destination_result(destination=destination)

    try:
        await _send_json(destination_socket, payload)
    except Exception:
        # Delivery failures are non-fatal and should not crash ingress loops.
        return _delivery_failed_result(destination=destination)

    return _routed_result(destination)
