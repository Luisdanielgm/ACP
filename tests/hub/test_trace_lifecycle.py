from __future__ import annotations


def test_agent_lifecycle_emits_connect_and_disconnect_trace(
    hello_frame, run_ingress, trace_sink, websocket_factory, assert_lifecycle_trace_sequence
) -> None:
    agent_socket = websocket_factory([hello_frame("agent_1", role="agent")])

    run_ingress(
        agent_socket,
        session_id="agent-session",
        active_agents={},
        trace_sink=trace_sink,
    )

    assert_lifecycle_trace_sequence(
        trace_sink,
        role="agent",
        name="agent_1",
        session_id="agent-session",
    )


def test_observer_lifecycle_emits_connect_disconnect_with_snapshot_first(
    hello_frame, run_ingress, trace_sink, websocket_factory, assert_lifecycle_trace_sequence
) -> None:
    observer_socket = websocket_factory([hello_frame("observer_1", role="observer")])

    run_ingress(
        observer_socket,
        session_id="observer-session",
        active_agents={},
        trace_sink=trace_sink,
    )

    assert observer_socket.sent[0] == {"type": "SNAPSHOT", "agents": []}
    assert observer_socket.sent[1]["type"] == "TRACE"
    assert observer_socket.sent[1]["event"] == "CONNECT"
    assert observer_socket.sent[1]["role"] == "observer"
    assert observer_socket.sent[1]["name"] == "observer_1"

    assert_lifecycle_trace_sequence(
        trace_sink,
        role="observer",
        name="observer_1",
        session_id="observer-session",
    )
