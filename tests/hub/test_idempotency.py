from __future__ import annotations

from acp.hub.migrations import apply_sqlite_migrations
from acp.hub.sqlite_support import connect


def test_migration_creates_idempotency_ledger(tmp_path) -> None:
    # C-REL-04: migration 0006 adds the message idempotency ledger table.
    db = tmp_path / "acp.sqlite3"
    apply_sqlite_migrations(sqlite_path=db)
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='message_idempotency'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_record_if_new_dedups_by_scope(tmp_path) -> None:
    # The dedup contract: a delivery is unique per (session_id, recipient, message_id).
    from acp.hub.idempotency import record_if_new

    db = tmp_path / "acp.sqlite3"
    apply_sqlite_migrations(sqlite_path=db)
    conn = connect(db)
    try:
        assert record_if_new(conn, session_id="s", recipient="r", message_id="m1", processed_at="t1") is True
        # exact same scope -> duplicate
        assert record_if_new(conn, session_id="s", recipient="r", message_id="m1", processed_at="t2") is False
        # different message_id -> new
        assert record_if_new(conn, session_id="s", recipient="r", message_id="m2", processed_at="t3") is True
        # different recipient -> new
        assert record_if_new(conn, session_id="s", recipient="r2", message_id="m1", processed_at="t4") is True
        conn.commit()
    finally:
        conn.close()
