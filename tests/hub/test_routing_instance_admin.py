from __future__ import annotations


def test_build_instance_admin_router_is_importable() -> None:
    """The instance-admin router factory imports cleanly after the de-tangle move.

    Behaviour (workspace CRUD, audit log, invite-admin, require_instance_admin
    guard) is covered by the managed admin suites and the 90-route baseline;
    this guards the move itself.
    """
    from acp_managed.routing.instance_admin import build_instance_admin_router

    assert callable(build_instance_admin_router)
