from __future__ import annotations

from acp.hub.session_registry import SessionRegistry


def test_observer_snapshot_is_agent_only_sorted_and_precedes_first_trace(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)

    assert registry.register_agent(
        session_id="agent-z",
        websocket=websocket_factory(),
        name="zeta_agent",
    )
    assert registry.register_agent(
        session_id="agent-a",
        websocket=websocket_factory(),
        name="alpha_agent",
    )
    registry.register_observer(
        session_id="existing-observer",
        websocket=websocket_factory(),
        name="observer_existing",
    )
    assert registry.enable_observer_live_traces("existing-observer")

    observer_socket = websocket_factory([hello_frame("observer_new", role="observer")])

    run_ingress(
        observer_socket,
        session_id="observer-new-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert observer_socket.sent[0] == {
        "type": "SNAPSHOT",
        "agents": ["alpha_agent", "zeta_agent"],
    }
    first_trace = observer_socket.sent[1]
    assert first_trace["type"] == "TRACE"
    assert first_trace["event"] == "CONNECT"
    assert first_trace["role"] == "observer"
    assert first_trace["name"] == "observer_new"


def test_observer_snapshot_is_deterministic_when_no_agents_connected(
    hello_frame, run_ingress, trace_sink, websocket_factory
) -> None:
    observer_socket = websocket_factory([hello_frame("observer_empty", role="observer")])

    run_ingress(
        observer_socket,
        session_id="observer-empty-session",
        active_agents={},
        trace_sink=trace_sink,
    )

    assert observer_socket.sent[0] == {"type": "SNAPSHOT", "agents": []}
    assert observer_socket.sent[1]["type"] == "TRACE"
    assert observer_socket.sent[1]["event"] == "CONNECT"
    assert observer_socket.sent[1]["name"] == "observer_empty"
