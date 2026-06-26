from __future__ import annotations

import pytest

pytest.skip(
    "legacy dashboard_html module was retired in favor of managed/public Vue dashboards; kept only as historical Phase 4 evidence text.",
    allow_module_level=True,
)

from acp.hub.dashboard_html import (
    DASHBOARD_HTML,
    FILTER_ALL,
    FILTER_CONNECT,
    FILTER_ERROR,
    FILTER_ROUTE,
    MAX_LOG_EVENTS,
    append_bounded_log,
    apply_trace_to_nodes,
    filter_trace_events,
    normalize_filter_mode,
    should_animate_route,
    snapshot_to_nodes,
)


def _trace(event: str, **kwargs: object) -> dict[str, object]:
    payload: dict[str, object] = {"type": "TRACE", "event": event, "ts": "2026-03-04T00:00:00Z"}
    payload.update(kwargs)
    return payload


def test_dashboard_endpoint_serves_hub_shell(api_client) -> None:
    response = api_client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "ACP Hub Dashboard" in body
    assert "Sesiones activas" in body
    assert "Trazas recientes del hub" in body
    assert 'lang="es"' in body
    assert "/dashboard/overview" in body
    assert "lang_switch_aria" in body
    assert "poll_active_title" in body


def test_dashboard_html_contains_runtime_constants_for_operator_contract() -> None:
    assert f"MAX_LOG = {MAX_LOG_EVENTS}" in DASHBOARD_HTML
    assert "ROUTE_ANIMATION_MS" in DASHBOARD_HTML
    assert "token-input" in DASHBOARD_HTML
    assert "trace-log" in DASHBOARD_HTML
    assert "/dashboard/auth/login" in DASHBOARD_HTML
    assert "Inicia sesion admin con ACP_TOKEN" in DASHBOARD_HTML


def test_dashboard_html_exposes_global_layout_controls() -> None:
    assert "id=\"sessions\"" in DASHBOARD_HTML
    assert "id=\"metrics\"" in DASHBOARD_HTML
    assert "id=\"squad-map\"" in DASHBOARD_HTML
    assert "id=\"hot-tasks\"" in DASHBOARD_HTML
    assert "id=\"recovery-feed\"" in DASHBOARD_HTML
    assert "id=\"task-ledger\"" in DASHBOARD_HTML
    assert "id=\"clear-btn\"" in DASHBOARD_HTML
    assert "id=\"login-btn\"" in DASHBOARD_HTML
    assert "id=\"logout-btn\"" in DASHBOARD_HTML
    assert "id=\"dashboard-filter-input\"" in DASHBOARD_HTML
    assert "id=\"dashboard-issues-filter\"" in DASHBOARD_HTML
    assert "id=\"traffic-status\"" in DASHBOARD_HTML
    assert "id=\"edit-access-btn\"" in DASHBOARD_HTML
    assert "grid-template-columns" in DASHBOARD_HTML
    assert "acp_session_dashboard_hint" in DASHBOARD_HTML


def test_dashboard_endpoint_contains_required_filters_and_layout_contract() -> None:
    assert "/dashboard/overview" in DASHBOARD_HTML
    assert "token-input" in DASHBOARD_HTML
    assert "Sesiones activas" in DASHBOARD_HTML
    assert "/dashboard/auth/session" in DASHBOARD_HTML
    assert "data-session-id=" in DASHBOARD_HTML


def test_dashboard_html_exposes_split_panel_and_clear_control() -> None:
    assert "id=\"sessions\"" in DASHBOARD_HTML
    assert "id=\"trace-log\"" in DASHBOARD_HTML
    assert "function escapeHtml" in DASHBOARD_HTML
    assert "id=\"clear-btn\"" in DASHBOARD_HTML


def test_snapshot_or_nodes_projection_from_snapshot_and_lifecycle_traces() -> None:
    nodes = snapshot_to_nodes({"agents": ["agent_z", "agent_a", "bad name", 7]})
    assert nodes == {"agent_z", "agent_a"}

    nodes = apply_trace_to_nodes(nodes, _trace("CONNECT", role="agent", name="agent_b"))
    assert nodes == {"agent_z", "agent_a", "agent_b"}

    nodes = apply_trace_to_nodes(nodes, _trace("DISCONNECT", role="agent", name="agent_z"))
    assert nodes == {"agent_a", "agent_b"}


def test_snapshot_or_nodes_ignores_non_agent_lifecycle_and_non_trace_frames() -> None:
    nodes = {"agent_a"}
    nodes = apply_trace_to_nodes(nodes, _trace("CONNECT", role="observer", name="observer_1"))
    assert nodes == {"agent_a"}

    nodes = apply_trace_to_nodes(nodes, {"type": "SNAPSHOT", "agents": ["agent_b"]})
    assert nodes == {"agent_a"}


def test_filters_single_mode_respects_all_route_error_connect() -> None:
    events = [
        _trace("ROUTE", **{"from": "a", "to": "b"}),
        _trace("ERROR", requested_to="missing"),
        _trace("CONNECT", role="agent", name="agent_a"),
        _trace("DROP", reason_code="INVALID_JSON"),
    ]

    all_events = filter_trace_events(events, mode=FILTER_ALL)
    route_events = filter_trace_events(events, mode=FILTER_ROUTE)
    error_events = filter_trace_events(events, mode=FILTER_ERROR)
    connect_events = filter_trace_events(events, mode=FILTER_CONNECT)

    assert len(all_events) == 4
    assert [event["event"] for event in route_events] == ["ROUTE"]
    assert [event["event"] for event in error_events] == ["ERROR"]
    assert [event["event"] for event in connect_events] == ["CONNECT"]


def test_filters_single_mode_unknown_value_falls_back_to_all() -> None:
    events = [_trace("ERROR"), _trace("ROUTE")]

    assert normalize_filter_mode("UNKNOWN") == FILTER_ALL
    assert normalize_filter_mode(None) == FILTER_ALL
    assert filter_trace_events(events, mode="UNKNOWN") == events


def test_route_animation_requires_known_nodes_and_route_event() -> None:
    nodes = {"agent_a", "agent_b"}

    assert should_animate_route(_trace("ROUTE", **{"from": "agent_a", "to": "agent_b"}), nodes) is True
    assert should_animate_route(_trace("ROUTE", **{"from": "agent_a", "to": "agent_a"}), nodes) is False
    assert should_animate_route(_trace("ROUTE", **{"from": "agent_a", "to": "agent_c"}), nodes) is False
    assert should_animate_route(_trace("ERROR", requested_to="agent_b"), nodes) is False


def test_route_animation_rejects_frames_without_required_fields() -> None:
    nodes = {"agent_a", "agent_b"}

    assert should_animate_route(_trace("ROUTE", **{"to": "agent_b"}), nodes) is False
    assert should_animate_route(_trace("ROUTE", **{"from": "agent_a"}), nodes) is False
    assert should_animate_route({"type": "TRACE", "event": "ROUTE", "from": 1, "to": "agent_b"}, nodes) is False


def test_bounded_log_window_under_high_volume_stream() -> None:
    history: list[dict[str, object]] = []

    for index in range(MAX_LOG_EVENTS + 25):
        history = append_bounded_log(history, _trace("ROUTE", seq=index), max_events=MAX_LOG_EVENTS)

    assert len(history) == MAX_LOG_EVENTS
    assert history[0]["seq"] == 25
    assert history[-1]["seq"] == MAX_LOG_EVENTS + 24


def test_bounded_log_window_respects_custom_cap() -> None:
    history: list[dict[str, object]] = []

    for index in range(6):
        history = append_bounded_log(history, _trace("ERROR", seq=index), max_events=3)

    assert len(history) == 3
    assert [item["seq"] for item in history] == [3, 4, 5]


def test_bounded_log_window_with_zero_cap_returns_empty() -> None:
    history = append_bounded_log([_trace("ROUTE")], _trace("ERROR"), max_events=0)
    assert history == []


def test_snapshot_to_nodes_handles_invalid_payload_shape() -> None:
    assert snapshot_to_nodes({"agents": "invalid"}) == set()
    assert snapshot_to_nodes({}) == set()


def test_apply_trace_to_nodes_reconnect_sequence_keeps_consistent_set() -> None:
    nodes = set()
    nodes = apply_trace_to_nodes(nodes, _trace("CONNECT", role="agent", name="agent_one"))
    nodes = apply_trace_to_nodes(nodes, _trace("DISCONNECT", role="agent", name="agent_one"))
    nodes = apply_trace_to_nodes(nodes, _trace("CONNECT", role="agent", name="agent_one"))
    assert nodes == {"agent_one"}


def test_append_bounded_log_returns_detached_copies() -> None:
    source_event = _trace("ERROR", reason_code="DESTINATION_NOT_FOUND")
    history = append_bounded_log([], source_event, max_events=5)

    source_event["reason_code"] = "MUTATED"
    assert history[0]["reason_code"] == "DESTINATION_NOT_FOUND"


def test_filter_trace_events_preserves_original_order() -> None:
    events = [
        _trace("ERROR", seq=1),
        _trace("ROUTE", seq=2),
        _trace("ERROR", seq=3),
        _trace("ROUTE", seq=4),
    ]

    filtered = filter_trace_events(events, mode=FILTER_ERROR)
    assert [event["seq"] for event in filtered] == [1, 3]


def test_filter_trace_events_returns_detached_copies() -> None:
    events = [_trace("ROUTE", seq=1)]
    filtered = filter_trace_events(events, mode=FILTER_ALL)

    filtered[0]["seq"] = 99
    assert events[0]["seq"] == 1


def test_apply_trace_to_nodes_ignores_invalid_agent_names() -> None:
    nodes = apply_trace_to_nodes(set(), _trace("CONNECT", role="agent", name="bad name"))
    assert nodes == set()

    nodes = apply_trace_to_nodes(nodes, _trace("CONNECT", role="agent", name="agent_valid"))
    assert nodes == {"agent_valid"}


def test_normalize_filter_mode_accepts_known_modes() -> None:
    assert normalize_filter_mode("ROUTE") == "ROUTE"
