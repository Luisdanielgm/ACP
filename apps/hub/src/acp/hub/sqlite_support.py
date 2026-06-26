"""Shared sqlite connection helper (C-REL-03).

Single source for the durability PRAGMAs (WAL journal + busy_timeout) so every
store opens connections consistently. row_factory and foreign_keys are opt-in
per store to preserve each store's existing behavior.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(
    db_path: str | Path,
    *,
    row_factory: bool = False,
    foreign_keys: bool = False,
    timeout: float = 30,
) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
