from __future__ import annotations

import sqlite3


def test_connect_applies_wal_and_busy_timeout(tmp_path) -> None:
    # C-REL-03: the shared sqlite connect helper applies the durability PRAGMAs.
    from acp.hub.sqlite_support import connect

    conn = connect(tmp_path / "t.sqlite3")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert conn.row_factory is None
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        conn.close()


def test_connect_optional_row_factory_and_foreign_keys(tmp_path) -> None:
    from acp.hub.sqlite_support import connect

    conn = connect(tmp_path / "t.sqlite3", row_factory=True, foreign_keys=True)
    try:
        assert conn.row_factory is sqlite3.Row
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()
