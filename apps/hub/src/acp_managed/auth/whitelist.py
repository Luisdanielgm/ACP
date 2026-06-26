"""Whitelist parsing helpers for the managed overlay."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedPrincipal:
    email: str
    password_hash: str
    role: str
    status: str


def build_principals_from_env(raw_value: str | None) -> list[ManagedPrincipal]:
    principals: list[ManagedPrincipal] = []
    if not isinstance(raw_value, str) or not raw_value.strip():
        return principals
    for entry in raw_value.split(";"):
        item = entry.strip()
        if not item:
            continue
        email, separator, remainder = item.partition("=")
        if not separator:
            continue
        password_hash, separator, tail = remainder.partition(":")
        if not separator:
            continue
        role, separator, status = tail.partition(",")
        if not separator:
            continue
        normalized_email = email.strip().lower()
        if not normalized_email:
            continue
        principals.append(
            ManagedPrincipal(
                email=normalized_email,
                password_hash=password_hash.strip(),
                role=role.strip() or "workspace_member",
                status=status.strip() or "active",
            )
        )
    return principals
