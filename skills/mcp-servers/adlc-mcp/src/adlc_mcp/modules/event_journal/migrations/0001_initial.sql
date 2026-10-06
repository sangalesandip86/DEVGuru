-- Event Journal: append-only, hash-chained per run_id. Owned by event_journal.db.
CREATE TABLE journal_entries (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    id            TEXT NOT NULL UNIQUE,
    run_id        TEXT NOT NULL,
    change_set_id TEXT NOT NULL DEFAULT '',
    event_type    TEXT NOT NULL,
    actor_type    TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    agent_role    TEXT NOT NULL DEFAULT '',
    payload       TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    visibility    TEXT NOT NULL DEFAULT 'INTERNAL'
);
CREATE INDEX idx_journal_run ON journal_entries (run_id);
CREATE INDEX idx_journal_change_set ON journal_entries (change_set_id);
CREATE INDEX idx_journal_event_type ON journal_entries (event_type);
