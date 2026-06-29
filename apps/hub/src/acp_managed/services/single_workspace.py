"""Single-workspace bootstrap for public self-host deployments."""

from __future__ import annotations

from uuid import uuid4

from acp_managed.auth.sqlite_store import (
    ManagedWorkspace,
    ManagedWorkspaceMembership,
    SqliteManagedPrincipalStore,
)
from acp_managed.auth.whitelist import ManagedPrincipal
from acp_managed.config import SingleWorkspaceSettings, single_workspace_settings


class SingleWorkspaceBootstrapError(RuntimeError):
    """Raised when a single-workspace deployment has incompatible auth state."""


def ensure_single_workspace_bootstrap(
    store: SqliteManagedPrincipalStore,
    *,
    settings: SingleWorkspaceSettings | None = None,
) -> ManagedWorkspace:
    """Ensure a public self-host install has exactly one workspace and one admin.

    Existing data is never deleted or rewritten. Multi-workspace databases fail
    fast because they belong to operator/cloud mode.
    """

    workspaces = store.list_workspaces()
    if len(workspaces) > 1:
        raise SingleWorkspaceBootstrapError(
            "single_workspace mode found multiple workspaces; use "
            "ACP_DEPLOYMENT_MODE=operator or start with a clean auth database"
        )
    if len(workspaces) == 1:
        return workspaces[0]

    if store.count() > 0:
        raise SingleWorkspaceBootstrapError(
            "single_workspace mode found principals but no workspace; start with "
            "a clean auth database or repair the workspace membership state"
        )

    bootstrap = settings or single_workspace_settings()
    principal = ManagedPrincipal(
        email=bootstrap.admin_email,
        password_hash=bootstrap.admin_password_hash,
        role="workspace_admin",
        status="active",
    )
    store.create(principal)
    workspace = ManagedWorkspace(
        workspace_id=f"ws_{uuid4().hex}",
        slug=bootstrap.slug,
        name=bootstrap.name,
        status="active",
        created_by=principal.email,
    )
    store.create_workspace(workspace)
    store.add_workspace_membership(
        ManagedWorkspaceMembership(
            workspace_id=workspace.workspace_id,
            email=principal.email,
            role="workspace_admin",
            status="active",
        )
    )
    return workspace
