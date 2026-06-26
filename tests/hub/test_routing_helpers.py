from __future__ import annotations


def test_handler_free_helpers_moved_to_routing_helpers() -> None:
    # A-DETANGLE-01: the handler-free helpers now live in
    # acp_managed.routing._helpers (extracted from the app.py god-file).
    from acp_managed.routing import _helpers

    # exercise the pure ones to prove they work from the new home
    assert _helpers._slugify_workspace_name("Hola Mundo!!") == "hola-mundo"
    assert _helpers._slugify_workspace_name("   ") == "espacio"
    event = _helpers._managed_replay_event_from_history(
        session_id="s1", item={"event_id": "e1", "event": "REPLY", "ts": "t"}
    )
    assert event["event_type"] == "reply"
    assert event["payload"]["session_id"] == "s1"

    # the full handler-free set must be importable from the new path
    for name in (
        "_sanitize_principal",
        "_sanitize_workspace",
        "_sanitize_membership",
        "_sanitize_workspace_session",
        "_managed_session_aliases",
        "_managed_replay_event_from_history",
        "_filter_managed_replay_history",
        "_sanitize_agent_token",
        "_sanitize_workspace_admin_invitation",
        "_slugify_workspace_name",
        "_allocate_workspace_slug",
        "_default_agent_token_label",
        "_request_scheme",
        "_request_is_secure",
        "_request_origin",
        "_request_ws_origin",
        "_managed_agent_bootstrap_payload",
        "_session_dashboard_url",
        "_session_dashboard_fallback_url",
    ):
        assert hasattr(_helpers, name), name
