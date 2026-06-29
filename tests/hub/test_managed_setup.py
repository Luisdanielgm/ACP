from __future__ import annotations

import pytest

from acp_managed.auth.passwords import verify_password
from acp_managed.setup import build_single_workspace_env, init_single_workspace_env, merge_env_lines


def test_build_single_workspace_env_generates_hash_and_separate_secrets() -> None:
    env = build_single_workspace_env(
        workspace_name="My Workspace",
        workspace_slug="default",
        admin_email="OWNER@EXAMPLE.COM",
        admin_password="admin-pass",
    )

    assert env["ACP_DEPLOYMENT_MODE"] == "single_workspace"
    assert env["ACP_WORKSPACE_SLUG"] == "default"
    assert env["ACP_WORKSPACE_ADMIN_EMAIL"] == "owner@example.com"
    assert verify_password("admin-pass", env["ACP_WORKSPACE_ADMIN_PASSWORD_HASH"])
    assert env["ACP_MANAGED_SESSION_SECRET"]
    assert env["ACP_MANAGED_AGENT_TOKEN_SECRET"]
    assert env["ACP_MANAGED_SESSION_SECRET"] != env["ACP_MANAGED_AGENT_TOKEN_SECRET"]


def test_build_single_workspace_env_rejects_weak_password() -> None:
    with pytest.raises(ValueError, match="at least 8"):
        build_single_workspace_env(
            workspace_name="My Workspace",
            workspace_slug="default",
            admin_email="owner@example.com",
            admin_password="short",
        )


def test_merge_env_lines_preserves_unrelated_values_and_quotes_spaces() -> None:
    merged = merge_env_lines(
        "# existing\nACP_PUBLIC_WEB_ENABLED=false\nACP_WORKSPACE_NAME=Old\n",
        {
            "ACP_WORKSPACE_NAME": "My Workspace",
            "ACP_WORKSPACE_SLUG": "default",
        },
    )

    assert "# existing" in merged
    assert "ACP_PUBLIC_WEB_ENABLED=false" in merged
    assert 'ACP_WORKSPACE_NAME="My Workspace"' in merged
    assert "ACP_WORKSPACE_SLUG=default" in merged


def test_init_single_workspace_env_writes_private_env_file(tmp_path) -> None:
    env_file = tmp_path / ".env"

    init_single_workspace_env(
        env_file=env_file,
        workspace_name="My Workspace",
        workspace_slug="default",
        admin_email="owner@example.com",
        admin_password="admin-pass",
    )

    content = env_file.read_text(encoding="utf-8")
    assert "ACP_DEPLOYMENT_MODE=single_workspace" in content
    assert "ACP_WORKSPACE_ADMIN_PASSWORD_HASH=\"scrypt$" in content
    assert "ACP_MANAGED_SESSION_SECRET=" in content
    assert "ACP_MANAGED_AGENT_TOKEN_SECRET=" in content
