ALTER TABLE coordination_members
    ADD COLUMN delivery_mode TEXT NOT NULL DEFAULT 'attached' CHECK (delivery_mode IN ('attached', 'runner'));

ALTER TABLE coordination_members
    ADD COLUMN provider TEXT NULL;

ALTER TABLE coordination_members
    ADD COLUMN workspace_path TEXT NULL;

ALTER TABLE coordination_members
    ADD COLUMN current_run_json TEXT NULL;

ALTER TABLE coordination_members
    ADD COLUMN last_run_json TEXT NULL;
