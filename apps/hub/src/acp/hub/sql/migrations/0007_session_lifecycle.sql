ALTER TABLE coordination_sessions
ADD COLUMN lifecycle_mode TEXT NOT NULL DEFAULT 'ephemeral'
CHECK (lifecycle_mode IN ('ephemeral', 'persistent'));
