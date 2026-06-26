"""Sqlite-backed managed principal store for the managed overlay."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from acp.hub.sqlite_support import connect
from acp_managed.auth.passwords import verify_password
from acp_managed.auth.whitelist import ManagedPrincipal


@dataclass(frozen=True)
class ManagedWorkspace:
    workspace_id: str
    slug: str
    name: str
    status: str
    created_by: str


@dataclass(frozen=True)
class ManagedWorkspaceMembership:
    workspace_id: str
    email: str
    role: str
    status: str


@dataclass(frozen=True)
class ManagedWorkspaceSessionRecord:
    session_id: str
    workspace_id: str
    created_by_email: str
    owner_agent_name: str
    owner_member_token: str | None
    title: str | None
    project: str | None
    created_at: str


@dataclass(frozen=True)
class ManagedBrowserSessionRecord:
    session_id: str
    email: str
    role: str
    token_hash: str
    issued_at: int
    expires_at: int


@dataclass(frozen=True)
class ManagedAgentTokenRecord:
    token_id: str
    workspace_id: str
    label: str
    agent_name: str | None
    token_hash: str
    token_hint: str
    status: str
    created_by_email: str
    created_at: int
    last_used_at: int | None


@dataclass(frozen=True)
class ManagedWorkspaceAdminInvitationRecord:
    invitation_id: str
    workspace_id: str
    email: str
    token_hash: str
    status: str
    created_by_email: str
    created_at: int
    expires_at: int
    accepted_at: int | None
    revoked_at: int | None


@dataclass(frozen=True)
class ManagedAuditEvent:
    audit_id: int
    created_at: int
    actor_email: str | None
    actor_ip: str | None
    action: str
    target_type: str | None
    target_id: str | None
    metadata_json: str | None


@dataclass
class SqliteManagedPrincipalStore:
    sqlite_path: Path | str

    def __post_init__(self) -> None:
        self._db_path = Path(self.sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return connect(self._db_path, row_factory=True, foreign_keys=True)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_principals (
                    email TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (created_by) REFERENCES managed_principals(email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_workspace_memberships (
                    workspace_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, email),
                    FOREIGN KEY (workspace_id) REFERENCES managed_workspaces(workspace_id) ON DELETE CASCADE,
                    FOREIGN KEY (email) REFERENCES managed_principals(email) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_workspace_sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    created_by_email TEXT NOT NULL,
                    owner_agent_name TEXT NOT NULL,
                    owner_member_token TEXT NULL,
                    title TEXT NULL,
                    project TEXT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (workspace_id) REFERENCES managed_workspaces(workspace_id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_email) REFERENCES managed_principals(email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_browser_sessions (
                    session_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    issued_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY (email) REFERENCES managed_principals(email) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_agent_tokens (
                    token_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    agent_name TEXT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    token_hint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by_email TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_used_at INTEGER NULL,
                    FOREIGN KEY (workspace_id) REFERENCES managed_workspaces(workspace_id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_email) REFERENCES managed_principals(email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_workspace_admin_invitations (
                    invitation_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_by_email TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    accepted_at INTEGER NULL,
                    revoked_at INTEGER NULL,
                    FOREIGN KEY (workspace_id) REFERENCES managed_workspaces(workspace_id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_email) REFERENCES managed_principals(email)
                )
                """
            )
            session_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(managed_workspace_sessions)").fetchall()
            }
            if "owner_member_token" not in session_columns:
                conn.execute(
                    """
                    ALTER TABLE managed_workspace_sessions
                    ADD COLUMN owner_member_token TEXT NULL
                    """
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    actor_email TEXT NULL,
                    actor_ip TEXT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NULL,
                    target_id TEXT NULL,
                    metadata_json TEXT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_managed_audit_log_created_at
                ON managed_audit_log(created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_managed_audit_log_actor_email
                ON managed_audit_log(actor_email)
                """
            )
            # Defensive cleanup for legacy rows that violated "single active" before
            # the unique indexes existed: keep only the newest active row per scope.
            conn.execute(
                """
                UPDATE managed_agent_tokens
                SET status = 'revoked'
                WHERE token_id IN (
                    SELECT token_id FROM (
                        SELECT
                            token_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY workspace_id
                                ORDER BY created_at DESC, token_id DESC
                            ) AS rn
                        FROM managed_agent_tokens
                        WHERE status = 'active' AND agent_name IS NULL
                    )
                    WHERE rn > 1
                )
                """
            )
            conn.execute(
                """
                UPDATE managed_agent_tokens
                SET status = 'revoked'
                WHERE token_id IN (
                    SELECT token_id FROM (
                        SELECT
                            token_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY workspace_id, agent_name
                                ORDER BY created_at DESC, token_id DESC
                            ) AS rn
                        FROM managed_agent_tokens
                        WHERE status = 'active' AND agent_name IS NOT NULL
                    )
                    WHERE rn > 1
                )
                """
            )
            # Enforce "single active workspace-scoped token per workspace" at the DB
            # level so concurrent rotations cannot both insert an active token.
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_managed_agent_tokens_active_workspace_scope
                ON managed_agent_tokens(workspace_id)
                WHERE status = 'active' AND agent_name IS NULL
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_managed_agent_tokens_active_agent_scope
                ON managed_agent_tokens(workspace_id, agent_name)
                WHERE status = 'active' AND agent_name IS NOT NULL
                """
            )
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) AS count FROM managed_principals").fetchone()
            return int(row["count"]) if row is not None else 0
        finally:
            conn.close()

    def count_active_by_role(self, role: str) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM managed_principals
                WHERE role = ? AND status = 'active'
                """,
                (role,),
            ).fetchone()
            return int(row["count"]) if row is not None else 0
        finally:
            conn.close()

    def upsert(self, principal: ManagedPrincipal) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO managed_principals(email, password_hash, role, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    status = excluded.status
                """,
                (principal.email, principal.password_hash, principal.role, principal.status),
            )
            conn.commit()
        finally:
            conn.close()

    def create(self, principal: ManagedPrincipal) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO managed_principals(email, password_hash, role, status)
                VALUES (?, ?, ?, ?)
                """,
                (principal.email, principal.password_hash, principal.role, principal.status),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("managed principal already exists") from exc
        finally:
            conn.close()

    def bootstrap_if_empty(self, principals: list[ManagedPrincipal]) -> int:
        if self.count() > 0:
            return 0
        inserted = 0
        for principal in principals:
            self.upsert(principal)
            inserted += 1
        return inserted

    def get(self, email: str) -> ManagedPrincipal | None:
        normalized = email.strip().lower()
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT email, password_hash, role, status
                FROM managed_principals
                WHERE email = ?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                return None
            return ManagedPrincipal(
                email=str(row["email"]),
                password_hash=str(row["password_hash"]),
                role=str(row["role"]),
                status=str(row["status"]),
            )
        finally:
            conn.close()

    def list_all(self) -> list[ManagedPrincipal]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT email, password_hash, role, status
                FROM managed_principals
                ORDER BY email ASC
                """
            ).fetchall()
            return [
                ManagedPrincipal(
                    email=str(row["email"]),
                    password_hash=str(row["password_hash"]),
                    role=str(row["role"]),
                    status=str(row["status"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def update_role_status(
        self,
        *,
        email: str,
        role: str | None = None,
        status: str | None = None,
    ) -> ManagedPrincipal:
        existing = self.get(email)
        if existing is None:
            raise ValueError("managed principal does not exist")
        updated = ManagedPrincipal(
            email=existing.email,
            password_hash=existing.password_hash,
            role=role or existing.role,
            status=status or existing.status,
        )
        self.upsert(updated)
        return updated

    def set_password_hash(self, *, email: str, password_hash: str) -> ManagedPrincipal:
        existing = self.get(email)
        if existing is None:
            raise ValueError("managed principal does not exist")
        updated = ManagedPrincipal(
            email=existing.email,
            password_hash=password_hash,
            role=existing.role,
            status=existing.status,
        )
        self.upsert(updated)
        return updated

    def delete(self, *, email: str) -> None:
        normalized = email.strip().lower()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM managed_principals WHERE email = ?",
                (normalized,),
            )
            conn.commit()
            if cursor.rowcount <= 0:
                raise ValueError("managed principal does not exist")
        finally:
            conn.close()

    def authenticate(self, *, email: str, password: str) -> ManagedPrincipal | None:
        principal = self.get(email)
        if principal is None:
            return None
        if principal.status != "active":
            return None
        if not verify_password(password, principal.password_hash):
            return None
        return principal

    def create_browser_session(self, record: ManagedBrowserSessionRecord) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO managed_browser_sessions(
                    session_id,
                    email,
                    role,
                    token_hash,
                    issued_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.email,
                    record.role,
                    record.token_hash,
                    record.issued_at,
                    record.expires_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_browser_session_by_token_hash(self, *, token_hash: str) -> ManagedBrowserSessionRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, email, role, token_hash, issued_at, expires_at
                FROM managed_browser_sessions
                WHERE token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            return ManagedBrowserSessionRecord(
                session_id=str(row["session_id"]),
                email=str(row["email"]),
                role=str(row["role"]),
                token_hash=str(row["token_hash"]),
                issued_at=int(row["issued_at"]),
                expires_at=int(row["expires_at"]),
            )
        finally:
            conn.close()

    def delete_browser_session_by_token_hash(self, *, token_hash: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM managed_browser_sessions WHERE token_hash = ?",
                (token_hash,),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_expired_browser_sessions(self, *, now_ts: int) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM managed_browser_sessions WHERE expires_at <= ?",
                (int(now_ts),),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def create_agent_token(self, record: ManagedAgentTokenRecord) -> None:
        conn = self._connect()
        try:
            if record.status == "active":
                if record.agent_name is None:
                    conn.execute(
                        """
                        UPDATE managed_agent_tokens
                        SET status = 'revoked'
                        WHERE workspace_id = ? AND status = 'active' AND agent_name IS NULL
                        """,
                        (record.workspace_id,),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE managed_agent_tokens
                        SET status = 'revoked'
                        WHERE workspace_id = ? AND status = 'active' AND agent_name = ?
                        """,
                        (record.workspace_id, record.agent_name),
                    )
            conn.execute(
                """
                INSERT INTO managed_agent_tokens(
                    token_id,
                    workspace_id,
                    label,
                    agent_name,
                    token_hash,
                    token_hint,
                    status,
                    created_by_email,
                    created_at,
                    last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.token_id,
                    record.workspace_id,
                    record.label,
                    record.agent_name,
                    record.token_hash,
                    record.token_hint,
                    record.status,
                    record.created_by_email,
                    record.created_at,
                    record.last_used_at,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("managed agent token already exists or references invalid data") from exc
        finally:
            conn.close()

    def list_agent_tokens_for_workspace(self, *, workspace_id: str) -> list[ManagedAgentTokenRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    token_id,
                    workspace_id,
                    label,
                    agent_name,
                    token_hash,
                    token_hint,
                    status,
                    created_by_email,
                    created_at,
                    last_used_at
                FROM managed_agent_tokens
                WHERE workspace_id = ?
                ORDER BY created_at DESC, token_id ASC
                """,
                (workspace_id,),
            ).fetchall()
            return [
                ManagedAgentTokenRecord(
                    token_id=str(row["token_id"]),
                    workspace_id=str(row["workspace_id"]),
                    label=str(row["label"]),
                    agent_name=str(row["agent_name"]) if row["agent_name"] is not None else None,
                    token_hash=str(row["token_hash"]),
                    token_hint=str(row["token_hint"]),
                    status=str(row["status"]),
                    created_by_email=str(row["created_by_email"]),
                    created_at=int(row["created_at"]),
                    last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_active_agent_token_for_workspace(self, *, workspace_id: str) -> ManagedAgentTokenRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT
                    token_id,
                    workspace_id,
                    label,
                    agent_name,
                    token_hash,
                    token_hint,
                    status,
                    created_by_email,
                    created_at,
                    last_used_at
                FROM managed_agent_tokens
                WHERE workspace_id = ? AND status = 'active' AND agent_name IS NULL
                ORDER BY created_at DESC, token_id DESC
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
            if row is None:
                return None
            return ManagedAgentTokenRecord(
                token_id=str(row["token_id"]),
                workspace_id=str(row["workspace_id"]),
                label=str(row["label"]),
                agent_name=str(row["agent_name"]) if row["agent_name"] is not None else None,
                token_hash=str(row["token_hash"]),
                token_hint=str(row["token_hint"]),
                status=str(row["status"]),
                created_by_email=str(row["created_by_email"]),
                created_at=int(row["created_at"]),
                last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
            )
        finally:
            conn.close()

    def get_agent_token(self, *, token_id: str) -> ManagedAgentTokenRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT
                    token_id,
                    workspace_id,
                    label,
                    agent_name,
                    token_hash,
                    token_hint,
                    status,
                    created_by_email,
                    created_at,
                    last_used_at
                FROM managed_agent_tokens
                WHERE token_id = ?
                LIMIT 1
                """,
                (token_id,),
            ).fetchone()
            if row is None:
                return None
            return ManagedAgentTokenRecord(
                token_id=str(row["token_id"]),
                workspace_id=str(row["workspace_id"]),
                label=str(row["label"]),
                agent_name=str(row["agent_name"]) if row["agent_name"] is not None else None,
                token_hash=str(row["token_hash"]),
                token_hint=str(row["token_hint"]),
                status=str(row["status"]),
                created_by_email=str(row["created_by_email"]),
                created_at=int(row["created_at"]),
                last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
            )
        finally:
            conn.close()

    def get_agent_token_by_hash(self, *, token_hash: str) -> ManagedAgentTokenRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT
                    token_id,
                    workspace_id,
                    label,
                    agent_name,
                    token_hash,
                    token_hint,
                    status,
                    created_by_email,
                    created_at,
                    last_used_at
                FROM managed_agent_tokens
                WHERE token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            return ManagedAgentTokenRecord(
                token_id=str(row["token_id"]),
                workspace_id=str(row["workspace_id"]),
                label=str(row["label"]),
                agent_name=str(row["agent_name"]) if row["agent_name"] is not None else None,
                token_hash=str(row["token_hash"]),
                token_hint=str(row["token_hint"]),
                status=str(row["status"]),
                created_by_email=str(row["created_by_email"]),
                created_at=int(row["created_at"]),
                last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
            )
        finally:
            conn.close()

    def revoke_agent_token(self, *, token_id: str) -> ManagedAgentTokenRecord:
        existing = self.get_agent_token(token_id=token_id)
        if existing is None:
            raise ValueError("managed agent token does not exist")
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE managed_agent_tokens
                SET status = 'revoked'
                WHERE token_id = ?
                """,
                (token_id,),
            )
            conn.commit()
        finally:
            conn.close()
        return ManagedAgentTokenRecord(
            token_id=existing.token_id,
            workspace_id=existing.workspace_id,
            label=existing.label,
            agent_name=existing.agent_name,
            token_hash=existing.token_hash,
            token_hint=existing.token_hint,
            status="revoked",
            created_by_email=existing.created_by_email,
            created_at=existing.created_at,
            last_used_at=existing.last_used_at,
        )

    def touch_agent_token(self, *, token_id: str, last_used_at: int) -> ManagedAgentTokenRecord:
        existing = self.get_agent_token(token_id=token_id)
        if existing is None:
            raise ValueError("managed agent token does not exist")
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE managed_agent_tokens
                SET last_used_at = ?
                WHERE token_id = ?
                """,
                (int(last_used_at), token_id),
            )
            conn.commit()
        finally:
            conn.close()
        return ManagedAgentTokenRecord(
            token_id=existing.token_id,
            workspace_id=existing.workspace_id,
            label=existing.label,
            agent_name=existing.agent_name,
            token_hash=existing.token_hash,
            token_hint=existing.token_hint,
            status=existing.status,
            created_by_email=existing.created_by_email,
            created_at=existing.created_at,
            last_used_at=int(last_used_at),
        )

    def create_workspace(self, workspace: ManagedWorkspace) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO managed_workspaces(workspace_id, slug, name, status, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    workspace.workspace_id,
                    workspace.slug,
                    workspace.name,
                    workspace.status,
                    workspace.created_by,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("managed workspace already exists or creator is invalid") from exc
        finally:
            conn.close()

    def get_workspace_by_slug(self, slug: str) -> ManagedWorkspace | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT workspace_id, slug, name, status, created_by
                FROM managed_workspaces
                WHERE slug = ?
                LIMIT 1
                """,
                (slug.strip().lower(),),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspace(
                workspace_id=str(row["workspace_id"]),
                slug=str(row["slug"]),
                name=str(row["name"]),
                status=str(row["status"]),
                created_by=str(row["created_by"]),
            )
        finally:
            conn.close()

    def get_workspace_by_id(self, workspace_id: str) -> ManagedWorkspace | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT workspace_id, slug, name, status, created_by
                FROM managed_workspaces
                WHERE workspace_id = ?
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspace(
                workspace_id=str(row["workspace_id"]),
                slug=str(row["slug"]),
                name=str(row["name"]),
                status=str(row["status"]),
                created_by=str(row["created_by"]),
            )
        finally:
            conn.close()

    def list_workspaces(self) -> list[ManagedWorkspace]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT workspace_id, slug, name, status, created_by
                FROM managed_workspaces
                ORDER BY slug ASC
                """
            ).fetchall()
            return [
                ManagedWorkspace(
                    workspace_id=str(row["workspace_id"]),
                    slug=str(row["slug"]),
                    name=str(row["name"]),
                    status=str(row["status"]),
                    created_by=str(row["created_by"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def update_workspace(
        self,
        *,
        slug: str,
        name: str | None = None,
        status: str | None = None,
    ) -> ManagedWorkspace:
        existing = self.get_workspace_by_slug(slug)
        if existing is None:
            raise ValueError("managed workspace does not exist")
        updated = ManagedWorkspace(
            workspace_id=existing.workspace_id,
            slug=existing.slug,
            name=name or existing.name,
            status=status or existing.status,
            created_by=existing.created_by,
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE managed_workspaces
                SET name = ?, status = ?
                WHERE slug = ?
                """,
                (updated.name, updated.status, updated.slug),
            )
            conn.commit()
        finally:
            conn.close()
        return updated

    def delete_workspace(self, *, slug: str) -> None:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM managed_workspaces WHERE slug = ?",
                (slug.strip().lower(),),
            )
            conn.commit()
            if cursor.rowcount <= 0:
                raise ValueError("managed workspace does not exist")
        finally:
            conn.close()

    def add_workspace_membership(self, membership: ManagedWorkspaceMembership) -> None:
        conn = self._connect()
        try:
            if membership.role == "workspace_admin" and membership.status == "active":
                existing = conn.execute(
                    """
                    SELECT email
                    FROM managed_workspace_memberships
                    WHERE workspace_id = ? AND role = 'workspace_admin' AND status = 'active' AND email != ?
                    LIMIT 1
                    """,
                    (membership.workspace_id, membership.email),
                ).fetchone()
                if existing is not None:
                    raise ValueError("workspace already has an active workspace_admin")
            conn.execute(
                """
                INSERT INTO managed_workspace_memberships(workspace_id, email, role, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workspace_id, email) DO UPDATE SET
                    role = excluded.role,
                    status = excluded.status
                """,
                (
                    membership.workspace_id,
                    membership.email,
                    membership.role,
                    membership.status,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("workspace or principal does not exist") from exc
        finally:
            conn.close()

    def get_workspace_admin_membership(self, *, workspace_id: str) -> ManagedWorkspaceMembership | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT workspace_id, email, role, status
                FROM managed_workspace_memberships
                WHERE workspace_id = ? AND role = 'workspace_admin' AND status = 'active'
                ORDER BY email ASC
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspaceMembership(
                workspace_id=str(row["workspace_id"]),
                email=str(row["email"]),
                role=str(row["role"]),
                status=str(row["status"]),
            )
        finally:
            conn.close()

    def remove_workspace_membership(self, *, workspace_id: str, email: str) -> None:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                DELETE FROM managed_workspace_memberships
                WHERE workspace_id = ? AND email = ?
                """,
                (workspace_id, email.strip().lower()),
            )
            conn.commit()
            if cursor.rowcount <= 0:
                raise ValueError("workspace membership does not exist")
        finally:
            conn.close()

    def list_workspace_memberships(self, *, workspace_id: str) -> list[ManagedWorkspaceMembership]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT workspace_id, email, role, status
                FROM managed_workspace_memberships
                WHERE workspace_id = ?
                ORDER BY email ASC
                """,
                (workspace_id,),
            ).fetchall()
            return [
                ManagedWorkspaceMembership(
                    workspace_id=str(row["workspace_id"]),
                    email=str(row["email"]),
                    role=str(row["role"]),
                    status=str(row["status"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def list_workspaces_for_email(self, *, email: str) -> list[ManagedWorkspaceMembership]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT workspace_id, email, role, status
                FROM managed_workspace_memberships
                WHERE email = ?
                ORDER BY workspace_id ASC
                """,
                (email.strip().lower(),),
            ).fetchall()
            return [
                ManagedWorkspaceMembership(
                    workspace_id=str(row["workspace_id"]),
                    email=str(row["email"]),
                    role=str(row["role"]),
                    status=str(row["status"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_membership(self, *, workspace_id: str, email: str) -> ManagedWorkspaceMembership | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT workspace_id, email, role, status
                FROM managed_workspace_memberships
                WHERE workspace_id = ? AND email = ?
                LIMIT 1
                """,
                (workspace_id, email.strip().lower()),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspaceMembership(
                workspace_id=str(row["workspace_id"]),
                email=str(row["email"]),
                role=str(row["role"]),
                status=str(row["status"]),
            )
        finally:
            conn.close()

    def create_workspace_session(self, record: ManagedWorkspaceSessionRecord) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO managed_workspace_sessions(
                    session_id,
                    workspace_id,
                    created_by_email,
                    owner_agent_name,
                    owner_member_token,
                    title,
                    project,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.workspace_id,
                    record.created_by_email,
                    record.owner_agent_name,
                    record.owner_member_token,
                    record.title,
                    record.project,
                    record.created_at,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("managed workspace session already exists or references invalid data") from exc
        finally:
            conn.close()

    def create_workspace_admin_invitation(self, record: ManagedWorkspaceAdminInvitationRecord) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE managed_workspace_admin_invitations
                SET status = 'revoked', revoked_at = ?
                WHERE workspace_id = ? AND status = 'pending'
                """,
                (record.created_at, record.workspace_id),
            )
            conn.execute(
                """
                INSERT INTO managed_workspace_admin_invitations(
                    invitation_id,
                    workspace_id,
                    email,
                    token_hash,
                    status,
                    created_by_email,
                    created_at,
                    expires_at,
                    accepted_at,
                    revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.invitation_id,
                    record.workspace_id,
                    record.email,
                    record.token_hash,
                    record.status,
                    record.created_by_email,
                    record.created_at,
                    record.expires_at,
                    record.accepted_at,
                    record.revoked_at,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("workspace admin invitation already exists or references invalid data") from exc
        finally:
            conn.close()

    def get_workspace_admin_invitation_by_hash(
        self,
        *,
        token_hash: str,
    ) -> ManagedWorkspaceAdminInvitationRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT
                    invitation_id,
                    workspace_id,
                    email,
                    token_hash,
                    status,
                    created_by_email,
                    created_at,
                    expires_at,
                    accepted_at,
                    revoked_at
                FROM managed_workspace_admin_invitations
                WHERE token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspaceAdminInvitationRecord(
                invitation_id=str(row["invitation_id"]),
                workspace_id=str(row["workspace_id"]),
                email=str(row["email"]),
                token_hash=str(row["token_hash"]),
                status=str(row["status"]),
                created_by_email=str(row["created_by_email"]),
                created_at=int(row["created_at"]),
                expires_at=int(row["expires_at"]),
                accepted_at=int(row["accepted_at"]) if row["accepted_at"] is not None else None,
                revoked_at=int(row["revoked_at"]) if row["revoked_at"] is not None else None,
            )
        finally:
            conn.close()

    def list_workspace_admin_invitations(self, *, workspace_id: str) -> list[ManagedWorkspaceAdminInvitationRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    invitation_id,
                    workspace_id,
                    email,
                    token_hash,
                    status,
                    created_by_email,
                    created_at,
                    expires_at,
                    accepted_at,
                    revoked_at
                FROM managed_workspace_admin_invitations
                WHERE workspace_id = ?
                ORDER BY created_at DESC, invitation_id ASC
                """,
                (workspace_id,),
            ).fetchall()
            return [
                ManagedWorkspaceAdminInvitationRecord(
                    invitation_id=str(row["invitation_id"]),
                    workspace_id=str(row["workspace_id"]),
                    email=str(row["email"]),
                    token_hash=str(row["token_hash"]),
                    status=str(row["status"]),
                    created_by_email=str(row["created_by_email"]),
                    created_at=int(row["created_at"]),
                    expires_at=int(row["expires_at"]),
                    accepted_at=int(row["accepted_at"]) if row["accepted_at"] is not None else None,
                    revoked_at=int(row["revoked_at"]) if row["revoked_at"] is not None else None,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def update_workspace_admin_invitation_status(
        self,
        *,
        invitation_id: str,
        status: str,
        accepted_at: int | None = None,
        revoked_at: int | None = None,
    ) -> ManagedWorkspaceAdminInvitationRecord:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT
                    invitation_id,
                    workspace_id,
                    email,
                    token_hash,
                    status,
                    created_by_email,
                    created_at,
                    expires_at,
                    accepted_at,
                    revoked_at
                FROM managed_workspace_admin_invitations
                WHERE invitation_id = ?
                LIMIT 1
                """,
                (invitation_id,),
            ).fetchone()
            if row is None:
                raise ValueError("workspace admin invitation does not exist")
            next_accepted_at = accepted_at if accepted_at is not None else row["accepted_at"]
            next_revoked_at = revoked_at if revoked_at is not None else row["revoked_at"]
            conn.execute(
                """
                UPDATE managed_workspace_admin_invitations
                SET status = ?, accepted_at = ?, revoked_at = ?
                WHERE invitation_id = ?
                """,
                (status, next_accepted_at, next_revoked_at, invitation_id),
            )
            conn.commit()
            return ManagedWorkspaceAdminInvitationRecord(
                invitation_id=str(row["invitation_id"]),
                workspace_id=str(row["workspace_id"]),
                email=str(row["email"]),
                token_hash=str(row["token_hash"]),
                status=status,
                created_by_email=str(row["created_by_email"]),
                created_at=int(row["created_at"]),
                expires_at=int(row["expires_at"]),
                accepted_at=int(next_accepted_at) if next_accepted_at is not None else None,
                revoked_at=int(next_revoked_at) if next_revoked_at is not None else None,
            )
        finally:
            conn.close()

    def cleanup_expired_workspace_admin_invitations(self, *, now_ts: int) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                UPDATE managed_workspace_admin_invitations
                SET status = 'expired'
                WHERE status = 'pending' AND expires_at <= ?
                """,
                (int(now_ts),),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def get_workspace_session(self, *, session_id: str) -> ManagedWorkspaceSessionRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, workspace_id, created_by_email, owner_agent_name, owner_member_token, title, project, created_at
                FROM managed_workspace_sessions
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return ManagedWorkspaceSessionRecord(
                session_id=str(row["session_id"]),
                workspace_id=str(row["workspace_id"]),
                created_by_email=str(row["created_by_email"]),
                owner_agent_name=str(row["owner_agent_name"]),
                owner_member_token=str(row["owner_member_token"]) if row["owner_member_token"] is not None else None,
                title=str(row["title"]) if row["title"] is not None else None,
                project=str(row["project"]) if row["project"] is not None else None,
                created_at=str(row["created_at"]),
            )
        finally:
            conn.close()

    def list_workspace_sessions(self, *, workspace_id: str) -> list[ManagedWorkspaceSessionRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, workspace_id, created_by_email, owner_agent_name, owner_member_token, title, project, created_at
                FROM managed_workspace_sessions
                WHERE workspace_id = ?
                ORDER BY created_at DESC, session_id ASC
                """,
                (workspace_id,),
            ).fetchall()
            return [
                ManagedWorkspaceSessionRecord(
                    session_id=str(row["session_id"]),
                    workspace_id=str(row["workspace_id"]),
                    created_by_email=str(row["created_by_email"]),
                    owner_agent_name=str(row["owner_agent_name"]),
                    owner_member_token=str(row["owner_member_token"]) if row["owner_member_token"] is not None else None,
                    title=str(row["title"]) if row["title"] is not None else None,
                    project=str(row["project"]) if row["project"] is not None else None,
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def delete_workspace_session(self, *, session_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                DELETE FROM managed_workspace_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            )
            conn.commit()
            return int(cursor.rowcount or 0) > 0
        finally:
            conn.close()

    def append_audit_event(
        self,
        *,
        action: str,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
        now_ts: int | None = None,
    ) -> int:
        import json as _json
        if not isinstance(action, str) or not action.strip():
            raise ValueError("audit event action is required")
        timestamp = int(now_ts if now_ts is not None else time.time())
        metadata_json = _json.dumps(metadata, ensure_ascii=True, sort_keys=True) if metadata else None
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO managed_audit_log(
                    created_at, actor_email, actor_ip, action, target_type, target_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    actor_email.strip().lower() if isinstance(actor_email, str) and actor_email.strip() else None,
                    actor_ip.strip() if isinstance(actor_ip, str) and actor_ip.strip() else None,
                    action.strip(),
                    target_type.strip() if isinstance(target_type, str) and target_type.strip() else None,
                    target_id.strip() if isinstance(target_id, str) and target_id.strip() else None,
                    metadata_json,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def list_audit_events(
        self,
        *,
        limit: int = 100,
        actor_email: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
    ) -> list[ManagedAuditEvent]:
        bounded_limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[object] = []
        if isinstance(actor_email, str) and actor_email.strip():
            clauses.append("actor_email = ?")
            params.append(actor_email.strip().lower())
        if isinstance(action, str) and action.strip():
            clauses.append("action = ?")
            params.append(action.strip())
        if isinstance(target_type, str) and target_type.strip():
            clauses.append("target_type = ?")
            params.append(target_type.strip())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(bounded_limit)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""
                SELECT audit_id, created_at, actor_email, actor_ip, action,
                       target_type, target_id, metadata_json
                FROM managed_audit_log
                {where}
                ORDER BY created_at DESC, audit_id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            return [
                ManagedAuditEvent(
                    audit_id=int(row["audit_id"]),
                    created_at=int(row["created_at"]),
                    actor_email=str(row["actor_email"]) if row["actor_email"] is not None else None,
                    actor_ip=str(row["actor_ip"]) if row["actor_ip"] is not None else None,
                    action=str(row["action"]),
                    target_type=str(row["target_type"]) if row["target_type"] is not None else None,
                    target_id=str(row["target_id"]) if row["target_id"] is not None else None,
                    metadata_json=str(row["metadata_json"]) if row["metadata_json"] is not None else None,
                )
                for row in rows
            ]
        finally:
            conn.close()
