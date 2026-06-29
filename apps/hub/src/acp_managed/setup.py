"""Setup helpers for ACP Managed self-host installs."""

from __future__ import annotations

import argparse
import getpass
import re
import secrets
from pathlib import Path

from acp_managed.auth.passwords import hash_password


_ENV_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_SAFE_ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _generate_secret() -> str:
    return secrets.token_urlsafe(48)


def _quote_env_value(value: str) -> str:
    if value and _SAFE_ENV_VALUE_RE.match(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _default_env_file() -> Path:
    if Path("apps/hub").is_dir():
        return Path("apps/hub/.env")
    return Path(".env")


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("admin email must be a valid email address")
    return normalized


def _normalize_slug(value: str) -> str:
    normalized = value.strip().lower()
    if not _SLUG_RE.match(normalized):
        raise ValueError("workspace slug must use lowercase letters, numbers, and dashes")
    return normalized


def build_single_workspace_env(
    *,
    workspace_name: str,
    workspace_slug: str,
    admin_email: str,
    admin_password: str,
    session_secret: str | None = None,
    agent_token_secret: str | None = None,
    sqlite_path: str = ".data/acp.sqlite3",
    managed_auth_sqlite_path: str = ".data/acp-managed-auth.sqlite3",
) -> dict[str, str]:
    """Build safe default env values for one public self-host workspace."""

    clean_name = workspace_name.strip()
    if not clean_name:
        raise ValueError("workspace name is required")
    if len(admin_password) < 8:
        raise ValueError("admin password must be at least 8 characters")

    return {
        "ACP_DEPLOYMENT_MODE": "single_workspace",
        "ACP_WORKSPACE_SLUG": _normalize_slug(workspace_slug),
        "ACP_WORKSPACE_NAME": clean_name,
        "ACP_WORKSPACE_ADMIN_EMAIL": _normalize_email(admin_email),
        "ACP_WORKSPACE_ADMIN_PASSWORD_HASH": hash_password(admin_password),
        "ACP_MANAGED_SESSION_SECRET": session_secret or _generate_secret(),
        "ACP_MANAGED_AGENT_TOKEN_SECRET": agent_token_secret or _generate_secret(),
        "ACP_PERSISTENCE_BACKEND": "sqlite",
        "ACP_SQLITE_PATH": sqlite_path,
        "ACP_MANAGED_AUTH_SQLITE_PATH": managed_auth_sqlite_path,
    }


def merge_env_lines(existing: str, updates: dict[str, str]) -> str:
    """Merge env updates while preserving unrelated comments and keys."""

    remaining = dict(updates)
    output: list[str] = []
    for line in existing.splitlines():
        match = _ENV_KEY_RE.match(line)
        if match is None:
            output.append(line)
            continue
        key = match.group(1)
        if key not in remaining:
            output.append(line)
            continue
        output.append(f"{key}={_quote_env_value(remaining.pop(key))}")

    if output and output[-1].strip():
        output.append("")
    output.extend(f"{key}={_quote_env_value(value)}" for key, value in remaining.items())
    return "\n".join(output).rstrip() + "\n"


def init_single_workspace_env(
    *,
    env_file: Path,
    workspace_name: str,
    workspace_slug: str,
    admin_email: str,
    admin_password: str,
) -> Path:
    updates = build_single_workspace_env(
        workspace_name=workspace_name,
        workspace_slug=workspace_slug,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(merge_env_lines(existing, updates), encoding="utf-8")
    return env_file


def _prompt_if_missing(value: str | None, prompt: str) -> str:
    if value is not None and value.strip():
        return value
    return input(prompt).strip()


def _password_if_missing(value: str | None) -> str:
    if value is not None and value:
        return value
    first = getpass.getpass("Admin password (min 8 chars): ")
    second = getpass.getpass("Confirm admin password: ")
    if first != second:
        raise ValueError("admin passwords do not match")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m acp_managed.setup")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-single-workspace",
        help="write a .env file for the public single-workspace ACP Manager",
    )
    init_parser.add_argument("--env-file", type=Path, default=None)
    init_parser.add_argument("--workspace-name")
    init_parser.add_argument("--workspace-slug", default="default")
    init_parser.add_argument("--admin-email")
    init_parser.add_argument("--admin-password")

    args = parser.parse_args(argv)
    if args.command == "init-single-workspace":
        env_file = args.env_file or _default_env_file()
        init_single_workspace_env(
            env_file=env_file,
            workspace_name=_prompt_if_missing(args.workspace_name, "Workspace name: "),
            workspace_slug=args.workspace_slug,
            admin_email=_prompt_if_missing(args.admin_email, "Admin email: "),
            admin_password=_password_if_missing(args.admin_password),
        )
        print(f"Wrote {env_file}")
        print("Keep the generated .env private. Do not commit it.")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
