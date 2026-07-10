ALTER TABLE coordination_pending_messages
    ADD COLUMN receipt_handle TEXT NULL;

ALTER TABLE coordination_pending_messages
    ADD COLUMN lease_expires_at TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_coordination_pending_messages_lease
    ON coordination_pending_messages(
        session_id,
        recipient_agent_name,
        lease_expires_at,
        priority_rank,
        sort_ts,
        queue_seq
    );
