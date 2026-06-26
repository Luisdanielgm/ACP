from __future__ import annotations


def test_build_workspace_admin_router_is_importable() -> None:
    """The workspace-admin router factory imports cleanly after the de-tangle move.

    Behaviour (agent-token mgmt, presets, dashboard, session-token rotate/revoke,
    session list/create/detail, owner_member_token exposure to admins) is covered
    by the managed workspace suites and the 90-route baseline; this guards the
    move itself.
    """
    from acp_managed.routing.workspace_admin import build_workspace_admin_router

    assert callable(build_workspace_admin_router)
