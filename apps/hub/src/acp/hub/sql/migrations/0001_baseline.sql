CREATE TABLE IF NOT EXISTS persisted_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_persisted_events_type ON persisted_events(event_type);

CREATE TABLE IF NOT EXISTS auth_principals (
    principal_id TEXT PRIMARY KEY,
    principal_name TEXT NOT NULL,
    scopes_csv TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_principals_name ON auth_principals(principal_name);

CREATE TABLE IF NOT EXISTS acl_rules (
    rule_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    action TEXT NOT NULL,
    allow INTEGER NOT NULL CHECK (allow IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_acl_rules_sender_recipient ON acl_rules(sender, recipient, action);
-- Phase 6 baseline intentionally excludes delivery/replay semantics.
