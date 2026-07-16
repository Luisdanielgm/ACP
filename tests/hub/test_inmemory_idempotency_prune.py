from __future__ import annotations

from acp.hub.coordination_store import InMemoryCoordinationStore


def test_inmemory_idempotency_prunes_by_processed_at() -> None:
    # The in-memory dedup ledger must honor its processed_at timestamp so a
    # long-lived (never-deleted) session's idempotency set does not grow forever.
    store = InMemoryCoordinationStore()

    assert store.record_delivery_if_new(
        session_id="s1", recipient="worker", message_id="m-old", processed_at="2026-07-01T00:00:00Z"
    )
    assert store.record_delivery_if_new(
        session_id="s1", recipient="worker", message_id="m-new", processed_at="2026-07-15T00:00:00Z"
    )

    removed = store.prune_idempotency_older_than("2026-07-10T00:00:00Z")
    assert removed == 1

    # The pruned key is forgotten (a retry would be treated as new); the recent
    # key is still remembered (a retry is still a duplicate).
    assert store.record_delivery_if_new(
        session_id="s1", recipient="worker", message_id="m-old", processed_at="2026-07-16T00:00:00Z"
    )
    assert not store.record_delivery_if_new(
        session_id="s1", recipient="worker", message_id="m-new", processed_at="2026-07-16T00:00:00Z"
    )
