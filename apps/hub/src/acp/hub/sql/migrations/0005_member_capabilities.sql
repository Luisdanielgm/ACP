ALTER TABLE coordination_members
    ADD COLUMN capabilities_json TEXT NOT NULL DEFAULT '[]';
