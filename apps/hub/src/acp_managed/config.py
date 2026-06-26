from __future__ import annotations

import os
import re

from acp_managed.auth.sqlite_store import SqliteManagedPrincipalStore
from acp_managed.auth.whitelist import build_principals_from_env

_INSECURE_SECRET_VALUES = {
    "changeme",
    "default",
    "defaultsecret",
    "devinsecuresecret",
    "password",
    "replaceme",
    "secret",
}


def normalize_secret_value(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def validated_managed_secret(secret: str | None, *, env_name: str) -> str:
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError(f"{env_name} is required and must not be empty")
    cleaned = secret.strip()
    if normalize_secret_value(cleaned) in _INSECURE_SECRET_VALUES:
        raise ValueError(f"{env_name} must be set to a strong non-placeholder secret")
    return cleaned


def public_web_enabled() -> bool:
    configured = os.getenv("ACP_PUBLIC_WEB_ENABLED")
    if configured is None:
        return False
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def managed_auth_sqlite_path() -> str:
    configured = os.getenv("ACP_MANAGED_AUTH_SQLITE_PATH")
    if not isinstance(configured, str) or not configured.strip():
        return ".data/acp-managed-auth.sqlite3"
    return configured.strip()


def managed_principal_store() -> SqliteManagedPrincipalStore:
    store = SqliteManagedPrincipalStore(sqlite_path=managed_auth_sqlite_path())
    store.bootstrap_if_empty(build_principals_from_env(os.getenv("ACP_MANAGED_WHITELIST")))
    return store


def managed_session_secret() -> str:
    return validated_managed_secret(
        os.getenv("ACP_MANAGED_SESSION_SECRET"),
        env_name="ACP_MANAGED_SESSION_SECRET",
    )


def managed_agent_token_secret() -> str:
    configured = os.getenv("ACP_MANAGED_AGENT_TOKEN_SECRET", "").strip()
    if configured:
        return validated_managed_secret(
            configured,
            env_name="ACP_MANAGED_AGENT_TOKEN_SECRET",
        )
    return managed_session_secret()


def managed_session_ttl_seconds() -> int:
    configured = os.getenv("ACP_MANAGED_SESSION_TTL_SECONDS")
    if not isinstance(configured, str) or not configured.strip():
        return 60 * 60 * 12
    try:
        return max(300, int(configured.strip()))
    except ValueError:
        return 60 * 60 * 12


def managed_invitation_ttl_seconds() -> int:
    configured = os.getenv("ACP_MANAGED_INVITATION_TTL_SECONDS")
    if not isinstance(configured, str) or not configured.strip():
        return 60 * 60 * 24 * 7
    try:
        return max(900, int(configured.strip()))
    except ValueError:
        return 60 * 60 * 24 * 7
