-- Work Planning (plan v3.1 §6 Module 4). Own database file; no shared tables.
-- Plan files are the source of truth; this is their projection as of the last ingested commit.

CREATE TABLE plan_commits (
    seq           INTEGER PRIMARY KEY,
    repository    TEXT NOT NULL,
    commit_sha    TEXT NOT NULL,
    item_count    INTEGER NOT NULL,
    full_snapshot INTEGER NOT NULL,
    ingested_by   TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    row_hash      TEXT NOT NULL
);
CREATE TRIGGER plan_commits_no_update BEFORE UPDATE ON plan_commits
BEGIN SELECT RAISE(ABORT, 'plan_commits is append-only'); END;
CREATE TRIGGER plan_commits_no_delete BEFORE DELETE ON plan_commits
BEGIN SELECT RAISE(ABORT, 'plan_commits is append-only'); END;

CREATE TABLE items (
    id          TEXT PRIMARY KEY,               -- REQ-n | EPIC-n | FEAT-n | ST-n | MS-n
    kind        TEXT NOT NULL,
    repository  TEXT NOT NULL,
    commit_sha  TEXT NOT NULL,
    path        TEXT,
    data        TEXT NOT NULL,                  -- JSON (the plan file; no status field)
    ac_hash     TEXT,                           -- stories only
    removed     INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);

CREATE TABLE edges (
    src       TEXT NOT NULL,
    dst       TEXT NOT NULL,
    relation  TEXT NOT NULL CHECK (relation IN ('scope','time','depends_on')),
    PRIMARY KEY (src, dst, relation)
);

-- Many-to-many Story <-> Change Set links.
CREATE TABLE links (
    story_id      TEXT NOT NULL,
    change_set_id TEXT NOT NULL,
    declared_in   TEXT NOT NULL,                -- the Implements: declaration it was validated against
    linked_by     TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    PRIMARY KEY (story_id, change_set_id)
);

-- Observed CI/forge facts that drive derived status (gate results, PRs opened, PO acceptance).
CREATE TABLE work_events (
    seq          INTEGER PRIMARY KEY,
    story_id     TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    ingested_by  TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    row_hash     TEXT NOT NULL
);
CREATE INDEX work_events_story ON work_events (story_id);
CREATE TRIGGER work_events_no_update BEFORE UPDATE ON work_events
BEGIN SELECT RAISE(ABORT, 'work_events is append-only'); END;
CREATE TRIGGER work_events_no_delete BEFORE DELETE ON work_events
BEGIN SELECT RAISE(ABORT, 'work_events is append-only'); END;

-- Derived status cache + its audit trail.
CREATE TABLE story_status (
    story_id    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE status_history (
    seq          INTEGER PRIMARY KEY,
    story_id     TEXT NOT NULL,
    from_status  TEXT,
    to_status    TEXT NOT NULL,
    reason       TEXT,
    timestamp    TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    row_hash     TEXT NOT NULL
);
CREATE TRIGGER wp_status_history_no_update BEFORE UPDATE ON status_history
BEGIN SELECT RAISE(ABORT, 'status_history is append-only'); END;
CREATE TRIGGER wp_status_history_no_delete BEFORE DELETE ON status_history
BEGIN SELECT RAISE(ABORT, 'status_history is append-only'); END;
