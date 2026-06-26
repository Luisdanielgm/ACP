CREATE INDEX IF NOT EXISTS idx_persisted_events_created_event
ON persisted_events(created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_persisted_events_type_created_event
ON persisted_events(event_type, created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_persisted_events_msg_created_event
ON persisted_events(json_extract(payload_json, '$.msg_id'), created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_persisted_events_thread_created_event
ON persisted_events(json_extract(payload_json, '$.thread_id'), created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_persisted_events_from_created_event
ON persisted_events(json_extract(payload_json, '$.from'), created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_persisted_events_to_created_event
ON persisted_events(json_extract(payload_json, '$.to'), created_at, event_id);

-- Replay read indexes are additive and preserve v0.1 send-route semantics.
-- Deterministic ordering is always keyed by (created_at, event_id).
