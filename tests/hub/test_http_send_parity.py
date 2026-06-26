from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from acp.hub.routing_service import (
    ROUTE_STATUS_DESTINATION_NOT_FOUND,
    ROUTE_STATUS_ROUTED,
    route_validated_msg,
)
from acp.hub.session_registry import SessionRegistry
from acp.protocol.models import MAX_PAYLOAD_BYTES


def _msg_body(*, sender: str, recipient: str, payload: str = "hello", msg_id: str | None = None) -> dict[str, str]:
    return {
        "id": msg_id or str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": payload,
    }


def test_ws_parity_baseline_shared_route_core_delivers(websocket_factory) -> None:
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    payload = {"type": "MSG", **_msg_body(sender="agent_sender", recipient="agent_receiver")}
    result = asyncio.run(route_validated_msg(payload=payload, active_agents=active_agents))

    assert result.status == ROUTE_STATUS_ROUTED
    assert receiver_socket.sent and receiver_socket.sent[0]["id"] == payload["id"]


def test_ws_parity_baseline_missing_destination_is_deterministic() -> None:
    payload = {"type": "MSG", **_msg_body(sender="agent_sender", recipient="agent_missing")}
    result = asyncio.run(route_validated_msg(payload=payload, active_agents={}))

    assert result.status == ROUTE_STATUS_DESTINATION_NOT_FOUND
    assert result.code == "INVALID_FIELD"
    assert result.field == "to"
    assert result.reason_code == "DESTINATION_NOT_FOUND"


def test_http_send_routes_valid_msg_and_emits_route_trace(api_client, hub_runtime, websocket_factory) -> None:
    receiver_socket = websocket_factory()
    assert hub_runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    payload = _msg_body(sender="orchestrator_1", recipient="agent_receiver")
    response = api_client.post("/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "id": payload["id"]}

    assert receiver_socket.sent and receiver_socket.sent[0]["id"] == payload["id"]
    route_events = [event for event in hub_runtime.trace_sink if event.get("event") == "ROUTE"]
    assert len(route_events) == 1
    assert route_events[0]["from"] == "orchestrator_1"
    assert route_events[0]["to"] == "agent_receiver"


def test_http_send_unknown_destination_returns_safe_error_and_trace(
    api_client,
    hub_runtime,
    observer_socket_factory,
) -> None:
    observer_socket = observer_socket_factory()
    hub_runtime.registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_live",
    )
    assert hub_runtime.registry.enable_observer_live_traces("observer-session")

    payload = _msg_body(sender="orchestrator_1", recipient="agent_missing")
    response = api_client.post("/send", json=payload)

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "INVALID_FIELD"
    assert body["field"] == "to"
    assert body["in_reply_to"] == payload["id"]

    sink_errors = [event for event in hub_runtime.trace_sink if event.get("event") == "ERROR"]
    assert len(sink_errors) == 1
    assert sink_errors[0]["reason_code"] == "DESTINATION_NOT_FOUND"
    assert sink_errors[0]["requested_to"] == "agent_missing"
    assert sink_errors[0]["in_reply_to"] == payload["id"]

    observer_errors = [event for event in observer_socket.sent if event.get("event") == "ERROR"]
    assert len(observer_errors) == 1
    assert observer_errors[0]["requested_to"] == "agent_missing"


def test_http_send_malformed_json_returns_safe_error(api_client) -> None:
    response = api_client.post(
        "/send",
        data='{"bad"',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "INVALID_JSON"


def test_http_send_payload_limit_maps_to_safe_error(api_client) -> None:
    response = api_client.post(
        "/send",
        json=_msg_body(
            sender="orchestrator_1",
            recipient="agent_missing",
            payload="x" * (MAX_PAYLOAD_BYTES + 1),
        ),
    )

    assert response.status_code == 413
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "PAYLOAD_TOO_LARGE"
    assert body["field"] == "payload"


def test_http_send_header_token_precedence_over_body_token(
    tokenized_api_client,
    tokenized_runtime,
    websocket_factory,
) -> None:
    receiver_socket = websocket_factory()
    assert tokenized_runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    payload = {
        **_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
        "token": "wrong-body-token",
    }
    response = tokenized_api_client.post(
        "/send",
        json=payload,
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_http_send_missing_required_token_returns_auth_required(tokenized_api_client) -> None:
    response = tokenized_api_client.post(
        "/send",
        json=_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert body["field"] == "token"


def test_http_send_invalid_token_returns_auth_invalid(tokenized_api_client) -> None:
    response = tokenized_api_client.post(
        "/send",
        json=_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
        headers={"X-ACP-Token": "wrong-token"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_INVALID"
    assert body["field"] == "token"

def test_http_send_unknown_destination_trace_is_allowlisted(
    api_client,
    hub_runtime,
    observer_socket_factory,
) -> None:
    observer_socket = observer_socket_factory()
    hub_runtime.registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_live",
    )
    assert hub_runtime.registry.enable_observer_live_traces("observer-session")

    payload = _msg_body(
        sender="orchestrator_1",
        recipient="agent_missing",
        payload='{"token":"secret","body":"hello"}',
    )
    response = api_client.post("/send", json=payload)

    assert response.status_code == 404
    trace_error = [event for event in observer_socket.sent if event.get("event") == "ERROR"][0]
    assert set(trace_error.keys()) == {
        "type",
        "event",
        "ts",
        "source_session",
        "reason_code",
        "requested_to",
        "in_reply_to",
    }


def test_http_send_rejects_non_msg_type_with_safe_error(api_client) -> None:
    payload = {
        "type": "HELLO",
        "role": "agent",
        "name": "agent_sender",
    }
    response = api_client.post("/send", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "INVALID_FIELD"
    assert body["field"] == "type"


def test_http_send_allows_body_token_fallback_when_header_missing(
    tokenized_api_client,
    tokenized_runtime,
    websocket_factory,
) -> None:
    receiver_socket = websocket_factory()
    assert tokenized_runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    payload = {
        **_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
        "token": "secret-token",
    }
    response = tokenized_api_client.post("/send", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
