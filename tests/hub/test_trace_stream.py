from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from acp.hub.session_registry import SessionRegistry


def _msg_frame(
    *,
    msg_id: str,
    sender: str,
    recipient: str,
    action: str = "TASK",
    payload: str = "hello",
) -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": msg_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": sender,
            "to": recipient,
            "action": action,
            "payload": payload,
        }
    )


def test_live_observer_receives_ordered_connect_route_drop_error_disconnect(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    live_observer = websocket_factory()
    registry.register_observer(
        session_id="observer-live-session",
        websocket=live_observer,
        name="observer_live",
    )
    assert registry.enable_observer_live_traces("observer-live-session")
    receiver_socket = websocket_factory()
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    routed_id = str(uuid4())
    error_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(msg_id=routed_id, sender="agent_sender", recipient="agent_receiver"),
            _msg_frame(
                msg_id=str(uuid4()),
                sender="agent_sender",
                recipient="agent_receiver",
                action="PING",
                payload='{"token":"super-secret"}',
            ),
            _msg_frame(
                msg_id=error_id,
                sender="agent_sender",
                recipient="agent_missing",
                payload='{"api_key":"dont-leak"}',
            ),
        ]
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    observer_events = [
        event
        for event in live_observer.sent
        if event.get("type") == "TRACE" and event.get("event") != "AUTHZ"
    ]
    assert [event["event"] for event in observer_events] == [
        "CONNECT",
        "ROUTE",
        "DROP",
        "ERROR",
        "DISCONNECT",
    ]

    assert receiver_socket.sent[0]["id"] == routed_id
    assert observer_events[1]["msg_id"] == routed_id
    assert observer_events[3]["in_reply_to"] == error_id
    assert set(observer_events[3].keys()) == {
        "type",
        "event",
        "ts",
        "source_session",
        "reason_code",
        "requested_to",
        "in_reply_to",
    }
    assert "token" not in str(observer_events[2])
    assert "api_key" not in str(observer_events[3])


def test_warmup_observer_is_excluded_from_live_trace_stream(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    live_observer = websocket_factory()
    warmup_observer = websocket_factory()
    registry.register_observer(
        session_id="observer-live-session",
        websocket=live_observer,
        name="observer_live",
    )
    assert registry.enable_observer_live_traces("observer-live-session")
    registry.register_observer(
        session_id="observer-warmup-session",
        websocket=warmup_observer,
        name="observer_warmup",
    )
    receiver_socket = websocket_factory()
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(
                msg_id=str(uuid4()),
                sender="agent_sender",
                recipient="agent_receiver",
            ),
        ]
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    live_events = [
        event["event"]
        for event in live_observer.sent
        if event.get("event") and event.get("event") != "AUTHZ"
    ]
    assert live_events == [
        "CONNECT",
        "ROUTE",
        "DISCONNECT",
    ]
    assert warmup_observer.sent == []
