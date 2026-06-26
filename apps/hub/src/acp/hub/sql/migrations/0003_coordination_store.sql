CREATE TABLE IF NOT EXISTS coordination_sessions (
    session_id TEXT PRIMARY KEY,
    join_code TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    title TEXT NULL,
    project TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_coordination_sessions_created_at
    ON coordination_sessions(created_at, session_id);

CREATE TABLE IF NOT EXISTS coordination_members (
    session_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    member_token TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('chief', 'collaborator')),
    status TEXT NOT NULL CHECK (status IN ('idle', 'waiting', 'busy')),
    status_text TEXT NULL,
    joined_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_message_at TEXT NULL,
    last_action TEXT NULL,
    current_task TEXT NULL,
    current_task_from TEXT NULL,
    current_task_at TEXT NULL,
    PRIMARY KEY (session_id, agent_name),
    FOREIGN KEY (session_id) REFERENCES coordination_sessions(session_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_coordination_members_agent_name
    ON coordination_members(agent_name);
CREATE INDEX IF NOT EXISTS idx_coordination_members_session
    ON coordination_members(session_id, agent_name);

CREATE TABLE IF NOT EXISTS coordination_pending_messages (
    queue_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    recipient_agent_name TEXT NOT NULL,
    priority_rank INTEGER NOT NULL,
    sort_ts TEXT NOT NULL,
    message_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    FOREIGN KEY (session_id, recipient_agent_name)
        REFERENCES coordination_members(session_id, agent_name)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_coordination_pending_messages_order
    ON coordination_pending_messages(session_id, recipient_agent_name, priority_rank, sort_ts, queue_seq);

CREATE TABLE IF NOT EXISTS coordination_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coordination_events_session
    ON coordination_events(session_id, event_seq);

CREATE TABLE IF NOT EXISTS coordination_member_notices (
    session_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    member_token TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, agent_name, member_token)
);
CREATE INDEX IF NOT EXISTS idx_coordination_member_notices_created_at
    ON coordination_member_notices(created_at);
