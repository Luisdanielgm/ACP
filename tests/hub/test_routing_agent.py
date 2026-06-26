from __future__ import annotations


def test_build_agent_router_is_importable() -> None:
    """The agent (Bearer) router factory imports cleanly after the de-tangle move.

    Behaviour (bootstrap, session create/list/detail/replay/join/close, the
    owner_member_token omission invariant) is covered by the managed agent
    suites and the 90-route baseline; this guards the move itself.
    """
    from acp_managed.routing.agent import build_agent_router

    assert callable(build_agent_router)
