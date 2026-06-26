from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from acp.hub.session_registry import SessionRegistry
from acp.protocol.errors import INVALID_FIELD


def _msg_frame(*, sender: str, recipient: str, action: str = "TASK", msg_id: str | None = None) -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": msg_id or str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": sender,
            "to": recipient,
            "action": action,
            "payload": "hello",
        }
    )


def test_registered_agent_routes_msg_to_connected_destination(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert len(receiver_socket.sent) == 1
    routed = receiver_socket.sent[0]
    assert routed["type"] == "MSG"
    assert routed["from"] == "agent_sender"
    assert routed["to"] == "agent_receiver"
    assert routed["action"] == "TASK"
    assert sender_socket.sent == []


def test_unregistered_sender_msg_is_rejected_safely(
    run_ingress, trace_sink, websocket_factory
) -> None:
    sender_socket = websocket_factory([_msg_frame(sender="agent_sender", recipient="agent_receiver")])

    run_ingress(
        sender_socket,
        session_id="unregistered-session",
        active_agents={},
        trace_sink=trace_sink,
    )

    assert sender_socket.sent[0]["action"] == "ERROR"
    assert sender_socket.sent[0]["code"] == INVALID_FIELD
    assert sender_socket.sent[0]["field"] == "from"
    assert trace_sink[0]["event"] == "DROP"


def test_observer_sender_msg_is_rejected_and_not_routed(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    observer_socket = websocket_factory(
        [
            hello_frame("observer_1", role="observer"),
            _msg_frame(sender="observer_1", recipient="agent_receiver"),
        ]
    )
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        observer_socket,
        session_id="observer-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert observer_socket.sent[0] == {"type": "SNAPSHOT", "agents": ["agent_receiver"]}
    assert observer_socket.sent[-1]["action"] == "ERROR"
    assert observer_socket.sent[-1]["code"] == INVALID_FIELD
    assert observer_socket.sent[-1]["field"] == "from"
    assert receiver_socket.sent == []


def test_forged_sender_name_is_rejected_and_not_routed(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(sender="agent_forged", recipient="agent_receiver"),
        ]
    )
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert sender_socket.sent[0]["action"] == "ERROR"
    assert sender_socket.sent[0]["code"] == INVALID_FIELD
    assert sender_socket.sent[0]["field"] == "from"
    assert receiver_socket.sent == []


def test_route_loop_stays_stable_when_destination_send_fails(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    class FlakyDestination:
        def __init__(self) -> None:
            self.sent: list[dict[str, str]] = []
            self._failed_once = False

        async def send_json(self, payload: dict[str, str]) -> None:
            if not self._failed_once:
                self._failed_once = True
                raise RuntimeError("destination disconnected")
            self.sent.append(payload)

    first_msg_id = str(uuid4())
    second_msg_id = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(
                sender="agent_sender",
                recipient="agent_flaky",
                msg_id=first_msg_id,
            ),
            _msg_frame(
                sender="agent_sender",
                recipient="agent_receiver",
                msg_id=second_msg_id,
            ),
        ]
    )
    receiver_socket = websocket_factory()
    flaky_socket = FlakyDestination()
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="flaky-session",
        websocket=flaky_socket,
        name="agent_flaky",
    )
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert sender_socket.closed is False
    assert receiver_socket.sent[0]["id"] == second_msg_id
    route_events = [event for event in trace_sink if event["event"] == "ROUTE"]
    assert len(route_events) == 1
    assert route_events[0]["msg_id"] == second_msg_id
