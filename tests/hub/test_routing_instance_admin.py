from __future__ import annotations

import importlib

import pytest


def test_instance_admin_router_was_removed_from_public_runtime() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("acp_managed.routing.instance_admin")
