from __future__ import annotations


def test_build_auth_router_is_importable() -> None:
    """The auth router factory imports cleanly after the de-tangle move.

    Behaviour (login/logout/invitation/me/session, rate limit, cookies) is
    covered by the managed smoke + auth suites and the 90-route baseline; this
    guards the move itself — that acp_managed.routing.auth imports without
    pulling a stale closure or a missing symbol.
    """
    from acp_managed.routing import ManagedRouterDeps
    from acp_managed.routing.auth import build_auth_router

    assert callable(build_auth_router)
    assert ManagedRouterDeps is not None
