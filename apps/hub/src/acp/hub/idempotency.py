"""Message idempotency contract + ledger primitive (C-REL-04).

Foundation for at-least-once delivery without observable duplicates. The dedup
scope is (session_id, recipient, message_id) derived from the message envelope's
id. C-REL-05/06 wire record_if_new() into the receive/ack paths; a future job
prunes ledger rows older than the retention window.
"""

from __future__ import annotations

import sqlite3

IDEMPOTENCY_TABLE = "message_idempotency"

# Retention window for ledger rows. Beyond this a replayed message_id may be
# treated as new; a future cleanup prunes rows older than this.
DEFAULT_IDEMPOTENCY_WINDOW_SECONDS = 86_400  # 24h


def idempotency_scope(*, session_id: str, recipient: str, message_id: str) -> tuple[str, str, str]:
    """The dedup key: a delivery is unique per (session, recipient, message)."""
    return (session_id, recipient, message_id)


def record_if_new(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    recipient: str,
    message_id: str,
    processed_at: str,
) -> bool:
    """Record a delivery in the ledger.

    Returns True if it is new (first time seen → caller should deliver/process),
    False if it is a duplicate (already recorded → caller should skip).
    """
    cursor = conn.execute(
        f"INSERT OR IGNORE INTO {IDEMPOTENCY_TABLE}"
        " (session_id, recipient, message_id, processed_at) VALUES (?, ?, ?, ?)",
        (session_id, recipient, message_id, processed_at),
    )
    return cursor.rowcount > 0
