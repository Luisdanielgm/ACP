from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from acp.hub.session_registry import SessionRegistry
from acp.protocol.errors import INVALID_FIELD


def _msg_frame(*, msg_id: str, sender: str, recipient: str, payload: str) -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": msg_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": sender,
            "to": recipient,
            "action": "TASK",
            "payload": payload,
        }
    )


def test_unknown_destination_sends_correlated_error_and_trace(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    observer_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_1",
    )
    assert registry.enable_observer_live_traces("observer-session")

    failed_msg_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(
                msg_id=failed_msg_id,
                sender="agent_sender",
                recipient="agent_missing",
                payload="secret=abc123",
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

    sender_error = sender_socket.sent[0]
    assert sender_error["action"] == "ERROR"
    assert sender_error["code"] == INVALID_FIELD
    assert sender_error["field"] == "to"
    assert sender_error["in_reply_to"] == failed_msg_id
    assert "abc123" not in sender_error["payload"]

    observer_errors = [event for event in observer_socket.sent if event.get("event") == "ERROR"]
    assert len(observer_errors) == 1
    trace_error = observer_errors[0]
    assert trace_error["reason_code"] == "DESTINATION_NOT_FOUND"
    assert trace_error["requested_to"] == "agent_missing"
    assert trace_error["in_reply_to"] == failed_msg_id

    sink_errors = [event for event in trace_sink if event.get("event") == "ERROR"]
    assert len(sink_errors) == 1
    assert sink_errors[0]["in_reply_to"] == failed_msg_id


def test_trace_error_payload_is_allowlisted(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    observer_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_1",
    )
    assert registry.enable_observer_live_traces("observer-session")

    failed_msg_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(
                msg_id=failed_msg_id,
                sender="agent_sender",
                recipient="agent_missing",
                payload='{"token":"super-secret","body":"hello"}',
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
    assert "token" not in trace_error
    assert "payload" not in trace_error
    assert "traceback" not in trace_error


def test_interleaved_route_and_error_events_keep_order_and_correlation(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    observer_socket = websocket_factory()
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_1",
    )
    assert registry.enable_observer_live_traces("observer-session")
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    first_msg_id = str(uuid4())
    failed_msg_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(
                msg_id=first_msg_id,
                sender="agent_sender",
                recipient="agent_receiver",
                payload="ok-1",
            ),
            _msg_frame(
                msg_id=failed_msg_id,
                sender="agent_sender",
                recipient="agent_missing",
                payload="will-fail",
            ),
            _msg_frame(
                msg_id=str(uuid4()),
                sender="agent_sender",
                recipient="agent_receiver",
                payload="ok-2",
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

    routed_ids = [message["id"] for message in receiver_socket.sent]
    assert routed_ids[0] == first_msg_id
    assert len(routed_ids) == 2

    sender_errors = [message for message in sender_socket.sent if message.get("action") == "ERROR"]
    assert len(sender_errors) == 1
    assert sender_errors[0]["in_reply_to"] == failed_msg_id

    observer_route_error_events = [
        event for event in observer_socket.sent if event.get("event") in {"ROUTE", "ERROR"}
    ]
    assert [event["event"] for event in observer_route_error_events] == ["ROUTE", "ERROR", "ROUTE"]
    assert observer_route_error_events[1]["reason_code"] == "DESTINATION_NOT_FOUND"
    assert observer_route_error_events[1]["requested_to"] == "agent_missing"
    assert observer_route_error_events[1]["in_reply_to"] == failed_msg_id
