from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from acp.hub.session_registry import SessionRegistry

_PHASE2_REQUIREMENTS = {"PROT-02", "HUB-01", "HUB-02", "HUB-03", "HUB-04"}
_SIGNAL_C_REQUIRED = {"HUB-02", "HUB-03", "HUB-04"}

_EVIDENCE_MATRIX = {
    "PROT-02": {"A", "B"},
    "HUB-01": {"A", "B"},
    "HUB-02": {"A", "B", "C"},
    "HUB-03": {"A", "B", "C"},
    "HUB-04": {"A", "B", "C"},
}


def _msg_frame(*, msg_id: str, sender: str, recipient: str, action: str = "TASK") -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": msg_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": sender,
            "to": recipient,
            "action": action,
            "payload": "payload",
        }
    )


def test_phase2_nyquist_matrix_requires_a_plus_b_and_adversarial_c() -> None:
    assert set(_EVIDENCE_MATRIX.keys()) == _PHASE2_REQUIREMENTS
    for requirement, signals in _EVIDENCE_MATRIX.items():
        assert {"A", "B"}.issubset(signals)
        if requirement in _SIGNAL_C_REQUIRED:
            assert "C" in signals


def test_hub02_signal_c_interleaved_route_error_keeps_correlation(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    observer_socket = websocket_factory()
    registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_live",
    )
    assert registry.enable_observer_live_traces("observer-session")
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=websocket_factory(),
        name="agent_receiver",
    )

    first_ok = str(uuid4())
    failed_id = str(uuid4())
    second_ok = str(uuid4())
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(msg_id=first_ok, sender="agent_sender", recipient="agent_receiver"),
            _msg_frame(msg_id=failed_id, sender="agent_sender", recipient="agent_missing"),
            _msg_frame(msg_id=second_ok, sender="agent_sender", recipient="agent_receiver"),
        ]
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    sender_errors = [message for message in sender_socket.sent if message.get("action") == "ERROR"]
    assert sender_errors[0]["in_reply_to"] == failed_id
    observer_route_errors = [
        event for event in observer_socket.sent if event.get("event") in {"ROUTE", "ERROR"}
    ]
    assert [event["event"] for event in observer_route_errors] == ["ROUTE", "ERROR", "ROUTE"]
    assert observer_route_errors[1]["in_reply_to"] == failed_id


def test_hub03_signal_c_snapshot_is_before_first_trace_for_new_observer(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="agent-session",
        websocket=websocket_factory(),
        name="agent_alpha",
    )
    observer_socket = websocket_factory([hello_frame("observer_new", role="observer")])

    run_ingress(
        observer_socket,
        session_id="observer-new-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert observer_socket.sent[0] == {"type": "SNAPSHOT", "agents": ["agent_alpha"]}
    assert observer_socket.sent[1]["type"] == "TRACE"
    assert observer_socket.sent[1]["event"] == "CONNECT"


def test_hub04_signal_c_full_stream_obeys_local_emission_order(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)
    observer_socket = websocket_factory()
    registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_live",
    )
    assert registry.enable_observer_live_traces("observer-session")
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=websocket_factory(),
        name="agent_receiver",
    )
    sender_socket = websocket_factory(
        [
            hello_frame("agent_sender", role="agent"),
            _msg_frame(msg_id=str(uuid4()), sender="agent_sender", recipient="agent_receiver"),
            _msg_frame(
                msg_id=str(uuid4()),
                sender="agent_sender",
                recipient="agent_receiver",
                action="PING",
            ),
            _msg_frame(msg_id=str(uuid4()), sender="agent_sender", recipient="agent_missing"),
        ]
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    expected_order = ["CONNECT", "ROUTE", "DROP", "ERROR", "DISCONNECT"]
    observer_order = [
        event["event"]
        for event in observer_socket.sent
        if event.get("event") and event.get("event") != "AUTHZ"
    ]
    sink_order = [
        event["event"]
        for event in trace_sink
        if event.get("source_session") == "sender-session" and event.get("event") != "AUTHZ"
    ]
    assert observer_order == expected_order
    assert sink_order == expected_order
