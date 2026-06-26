from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from acp.hub.app import create_runtime_from_env
from acp.hub.migrations import (
    MigrationError,
    SCHEMA_VERSION_TABLE,
    apply_migrations,
    apply_sqlite_migrations,
    discover_sql_migrations,
)


def _sqlite_row_count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def test_discover_sql_migrations_is_deterministic() -> None:
    artifacts = discover_sql_migrations()
    ids = [artifact.migration_id for artifact in artifacts]

    assert ids == sorted(ids)
    assert ids == ["0001", "0002", "0003", "0004", "0005", "0006"]


def test_apply_migrations_alias_matches_primary_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "alias.sqlite3"

    result = apply_migrations(sqlite_path=db_path)

    assert result.applied == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert _sqlite_row_count(db_path, SCHEMA_VERSION_TABLE) == 6


def test_apply_sqlite_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "phase6.sqlite3"

    first = apply_sqlite_migrations(sqlite_path=db_path)
    second = apply_sqlite_migrations(sqlite_path=db_path)

    assert first.applied == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert first.skipped == []
    assert second.applied == []
    assert second.skipped == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert _sqlite_row_count(db_path, "schema_migrations") == 6
    assert _sqlite_row_count(db_path, "persisted_events") == 0
    assert _sqlite_row_count(db_path, "auth_principals") == 0
    assert _sqlite_row_count(db_path, "acl_rules") == 0
    assert _sqlite_row_count(db_path, "coordination_sessions") == 0
    assert _sqlite_row_count(db_path, "coordination_members") == 0
    assert _sqlite_row_count(db_path, "coordination_pending_messages") == 0
    assert _sqlite_row_count(db_path, "coordination_events") == 0
    assert _sqlite_row_count(db_path, "coordination_member_notices") == 0


def test_apply_sqlite_migrations_fails_when_unknown_migration_id_present(tmp_path: Path) -> None:
    db_path = tmp_path / "invalid.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(migration_id, applied_at) VALUES ('9999', '2026-03-04T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(MigrationError, match="unknown applied migration ids"):
        apply_sqlite_migrations(sqlite_path=db_path)


def test_create_runtime_from_env_runs_sqlite_migrations_before_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "bootstrap.sqlite3"
    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(db_path))

    runtime = create_runtime_from_env()
    status = runtime.as_status_payload()

    assert runtime.migration_ready is True
    assert runtime.storage_ready is True
    assert status["migration_ready"] is True
    assert status["storage_ready"] is True
    assert "sqlite" not in str(status)
    assert _sqlite_row_count(db_path, "schema_migrations") == 6


def test_create_runtime_from_env_fails_on_invalid_sqlite_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "broken.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(migration_id, applied_at) VALUES ('9999', '2026-03-04T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ACP_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("ACP_SQLITE_PATH", str(db_path))

    with pytest.raises(RuntimeError, match="phase-6 migration bootstrap failed"):
        create_runtime_from_env()
