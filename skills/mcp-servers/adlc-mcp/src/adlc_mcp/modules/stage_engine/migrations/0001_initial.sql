CREATE TABLE IF NOT EXISTS stage_transitions (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT    NOT NULL UNIQUE,
    change_set_id TEXT  NOT NULL,
    from_stage  TEXT    NOT NULL,
    to_stage    TEXT    NOT NULL,
    actor_type  TEXT    NOT NULL CHECK(actor_type IN ('HUMAN', 'AGENT', 'SYSTEM')),
    actor_id    TEXT    NOT NULL,
    actor_role  TEXT    NOT NULL,
    outputs     TEXT    NOT NULL DEFAULT '[]',
    evidence_ids TEXT   NOT NULL DEFAULT '[]',
    gate_result TEXT,
    timestamp   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transitions_cs ON stage_transitions(change_set_id);
CREATE INDEX IF NOT EXISTS idx_transitions_stage ON stage_transitions(to_stage);

CREATE TABLE IF NOT EXISTS stage_current (
    change_set_id TEXT PRIMARY KEY,
    current_stage TEXT NOT NULL DEFAULT 'INTAKE',
    previous_stage TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL
);
