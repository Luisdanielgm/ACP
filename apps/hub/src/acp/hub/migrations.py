"""Deterministic SQL migration runner for phase-6 bootstrap."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class MigrationError(RuntimeError):
    """Raised when migration discovery or application is invalid."""


@dataclass(frozen=True)
class MigrationArtifact:
    migration_id: str
    path: Path


@dataclass(frozen=True)
class MigrationRunResult:
    applied: list[str]
    skipped: list[str]


SCHEMA_VERSION_TABLE = "schema_migrations"
MIGRATIONS_SQL_DIR = "sql/migrations"
REQUIRED_BOOTSTRAP_TABLES = {
    "persisted_events",
    "auth_principals",
    "acl_rules",
    "coordination_sessions",
    "coordination_members",
    "coordination_pending_messages",
    "coordination_events",
    "coordination_member_notices",
    SCHEMA_VERSION_TABLE,
}


def default_migrations_dir() -> Path:
    return Path(__file__).resolve().parent / MIGRATIONS_SQL_DIR


def discover_sql_migrations(*, migrations_dir: Path | None = None) -> list[MigrationArtifact]:
    source_dir = migrations_dir or default_migrations_dir()
    if not source_dir.exists():
        raise MigrationError(f"migrations directory not found: {source_dir}")

    artifacts: list[MigrationArtifact] = []
    seen_ids: set[str] = set()
    for sql_path in sorted(source_dir.glob("*.sql")):
        migration_id = sql_path.stem.split("_", 1)[0]
        if not migration_id:
            raise MigrationError(f"invalid migration filename: {sql_path.name}")
        if migration_id in seen_ids:
            raise MigrationError(f"duplicate migration id: {migration_id}")
        seen_ids.add(migration_id)
        artifacts.append(MigrationArtifact(migration_id=migration_id, path=sql_path))

    if not artifacts:
        raise MigrationError(f"no SQL migrations found in: {source_dir}")
    return artifacts


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    # schema_version tracking is persisted in schema_migrations for deterministic bootstrap.
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_VERSION_TABLE} (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _load_applied_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        f"SELECT migration_id FROM {SCHEMA_VERSION_TABLE} ORDER BY migration_id ASC"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _validate_known_ids(applied_ids: set[str], known_ids: set[str]) -> None:
    unknown = sorted(applied_ids - known_ids)
    if unknown:
        raise MigrationError(f"unknown applied migration ids detected: {', '.join(unknown)}")


def apply_sqlite_migrations(
    *,
    sqlite_path: Path | str,
    migrations_dir: Path | None = None,
) -> MigrationRunResult:
    artifacts = discover_sql_migrations(migrations_dir=migrations_dir)
    known_ids = {artifact.migration_id for artifact in artifacts}

    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    applied: list[str] = []
    skipped: list[str] = []

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema_migrations_table(conn)
        applied_ids = _load_applied_ids(conn)
        _validate_known_ids(applied_ids, known_ids)

        for artifact in artifacts:
            if artifact.migration_id in applied_ids:
                skipped.append(artifact.migration_id)
                continue

            sql = artifact.path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                f"INSERT INTO {SCHEMA_VERSION_TABLE}(migration_id, applied_at) VALUES (?, ?)",
                (
                    artifact.migration_id,
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ),
            )
            conn.commit()
            applied.append(artifact.migration_id)
            applied_ids.add(artifact.migration_id)
    except sqlite3.DatabaseError as exc:
        conn.rollback()
        raise MigrationError(f"sqlite migration failed: {exc}") from exc
    finally:
        conn.close()

    return MigrationRunResult(applied=applied, skipped=skipped)


def apply_migrations(*, sqlite_path: Path | str, migrations_dir: Path | None = None) -> MigrationRunResult:
    """Compatibility alias used by plan link verification patterns."""

    return apply_sqlite_migrations(sqlite_path=sqlite_path, migrations_dir=migrations_dir)


def verify_sqlite_bootstrap_state(
    *,
    sqlite_path: Path | str,
    migrations_dir: Path | None = None,
) -> None:
    """Fail fast if sqlite schema/version state is drifted or partially initialized."""

    artifacts = discover_sql_migrations(migrations_dir=migrations_dir)
    expected_ids = {artifact.migration_id for artifact in artifacts}

    conn = sqlite3.connect(Path(sqlite_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        existing_tables = {str(row[0]) for row in rows if row and row[0]}
        missing_tables = sorted(REQUIRED_BOOTSTRAP_TABLES - existing_tables)
        if missing_tables:
            raise MigrationError(
                f"sqlite bootstrap verification failed: missing tables: {', '.join(missing_tables)}"
            )

        cols = conn.execute(f"PRAGMA table_info({SCHEMA_VERSION_TABLE})").fetchall()
        column_names = {str(row[1]) for row in cols if len(row) >= 2 and row[1]}
        required_columns = {"migration_id", "applied_at"}
        missing_columns = sorted(required_columns - column_names)
        if missing_columns:
            raise MigrationError(
                f"sqlite bootstrap verification failed: schema_migrations missing columns: {', '.join(missing_columns)}"
            )

        applied_ids = _load_applied_ids(conn)
        missing_migrations = sorted(expected_ids - applied_ids)
        if missing_migrations:
            raise MigrationError(
                "sqlite bootstrap verification failed: missing applied migrations: "
                + ", ".join(missing_migrations)
            )
    except sqlite3.DatabaseError as exc:
        raise MigrationError(f"sqlite bootstrap verification failed: {exc}") from exc
    finally:
        conn.close()
