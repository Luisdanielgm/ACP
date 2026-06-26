from __future__ import annotations

from acp.hub.session_registry import SessionRegistry
from acp.protocol.errors import INVALID_FIELD


def test_duplicate_connected_agent_hello_rejects_only_new_socket(
    hello_frame, run_ingress, trace_sink, websocket_factory, assert_close_code
) -> None:
    existing_socket = websocket_factory()
    incoming = websocket_factory([hello_frame("agent_1", role="agent")])
    active_agents = {"agent_1": existing_socket}
    registry = SessionRegistry(active_agents=active_agents)

    run_ingress(
        incoming,
        session_id="incoming_1",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
    )

    assert_close_code(incoming, expected_code=1008, expected_reason="duplicate-agent-name")
    assert active_agents["agent_1"] is existing_socket
    assert incoming.sent[0]["code"] == INVALID_FIELD
    assert incoming.sent[0]["field"] == "name"
    assert any(event.get("event") == "DROP" for event in trace_sink)
    assert registry.get_session("incoming_1") is None


def test_registry_tracks_role_binding_and_live_trace_gate() -> None:
    active_agents: dict[str, object] = {}
    registry = SessionRegistry(active_agents=active_agents)

    agent_socket = object()
    observer_socket = object()

    assert registry.register_agent(session_id="agent-session", websocket=agent_socket, name="agent_1")
    agent = registry.get_session("agent-session")
    assert agent is not None
    assert agent.role == "agent"
    assert agent.name == "agent_1"
    assert active_agents["agent_1"] is agent_socket

    observer = registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_1",
    )
    assert observer.role == "observer"
    assert observer.live_trace_enabled is False
    assert registry.observer_sessions(live_only=True) == []
    assert registry.enable_observer_live_traces("observer-session") is True
    assert registry.observer_sessions(live_only=True)[0].name == "observer_1"
    assert registry.snapshot_agents() == ["agent_1"]

    removed_agent = registry.unregister_session(session_id="agent-session", websocket=agent_socket)
    assert removed_agent is not None
    assert removed_agent.role == "agent"
    assert registry.snapshot_agents() == []
