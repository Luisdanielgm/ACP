-- C-REL-04: message idempotency ledger.
-- Records processed deliveries so at-least-once retries do not duplicate.
-- Dedup scope is (session_id, recipient, message_id) from the envelope id.
CREATE TABLE IF NOT EXISTS message_idempotency (
    session_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (session_id, recipient, message_id)
);

-- processed_at index supports the future retention/window cleanup.
CREATE INDEX IF NOT EXISTS idx_message_idempotency_processed_at
    ON message_idempotency (processed_at);
