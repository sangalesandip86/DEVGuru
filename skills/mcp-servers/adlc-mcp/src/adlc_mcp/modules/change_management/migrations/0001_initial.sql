-- Change Management (plan §4.5, §6 Server 2). Own database file; no shared tables.

-- Current state of each Change Set. Mutable, but every status change is also appended
-- to the hash-chained status_history table, which is the audit record.
CREATE TABLE change_sets (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    system              TEXT,
    initiative          TEXT,
    requirements        TEXT NOT NULL,     -- JSON array
    repositories        TEXT NOT NULL,     -- JSON array of repo names
    contracts           TEXT NOT NULL,     -- JSON array
    environments        TEXT NOT NULL,     -- JSON array
    release_environment TEXT NOT NULL DEFAULT 'production',
    status              TEXT NOT NULL,
    blocked_from        TEXT,              -- state to return to when BLOCKED clears
    block_kind          TEXT,              -- GATE_FAILED | DEPENDENCY_UNMET | ESCALATION
    risk_tier           TEXT,              -- NULL = not computed (treated as HIGH)
    parent_id           TEXT REFERENCES change_sets(id),
    depends_on          TEXT NOT NULL,     -- JSON array of change set ids
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE status_history (
    seq            INTEGER PRIMARY KEY,
    change_set_id  TEXT NOT NULL,
    from_status    TEXT,
    to_status      TEXT NOT NULL,
    actor_type     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    via            TEXT NOT NULL,          -- update_status | forge_event:<id> | create
    reason         TEXT,
    timestamp      TEXT NOT NULL,
    prev_hash      TEXT NOT NULL,
    row_hash       TEXT NOT NULL
);
CREATE TRIGGER status_history_no_update BEFORE UPDATE ON status_history
BEGIN SELECT RAISE(ABORT, 'status_history is append-only'); END;
CREATE TRIGGER status_history_no_delete BEFORE DELETE ON status_history
BEGIN SELECT RAISE(ABORT, 'status_history is append-only'); END;

CREATE TABLE tasks (
    change_set_id  TEXT NOT NULL REFERENCES change_sets(id),
    id             TEXT NOT NULL,
    depends_on     TEXT NOT NULL,          -- JSON array of task ids
    owner_role     TEXT NOT NULL,
    worktree       TEXT,
    attempts       INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,          -- PENDING | IN_PROGRESS | DONE | BLOCKED
    blocked_reason TEXT,
    checkpoint     TEXT,                   -- JSON {commit_sha, ledger_cursor, snapshot_id}
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (change_set_id, id)
);

CREATE TABLE snapshots (
    id             TEXT PRIMARY KEY,
    change_set_id  TEXT NOT NULL REFERENCES change_sets(id),
    repositories   TEXT NOT NULL,          -- JSON {repo: commit_sha}
    contracts      TEXT NOT NULL,          -- JSON {contract_id: version}
    environments   TEXT NOT NULL,          -- JSON {env: state}
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE TRIGGER snapshots_no_update BEFORE UPDATE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;

CREATE TABLE dependencies (
    id             TEXT PRIMARY KEY,
    change_set_id  TEXT NOT NULL REFERENCES change_sets(id),
    source         TEXT NOT NULL,
    target         TEXT NOT NULL,
    type           TEXT NOT NULL,
    confidence     REAL NOT NULL,
    evidence_level TEXT NOT NULL CHECK (evidence_level IN ('DECLARED','STATIC','OBSERVED')),
    status         TEXT NOT NULL CHECK (status IN ('RESOLVED','UNRESOLVED')),
    recorded_by    TEXT NOT NULL,
    timestamp      TEXT NOT NULL
);
CREATE TRIGGER dependencies_no_delete BEFORE DELETE ON dependencies
BEGIN SELECT RAISE(ABORT, 'dependencies cannot be deleted; record a resolution instead'); END;

CREATE TABLE risk_assessments (
    seq            INTEGER PRIMARY KEY,
    change_set_id  TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('COMPUTED','HUMAN_OVERRIDE')),
    base_tier      TEXT,
    final_tier     TEXT NOT NULL,
    previous_tier  TEXT,
    direction      TEXT,                   -- UPGRADE | DOWNGRADE | NONE
    reason_codes   TEXT,                   -- JSON array
    detail         TEXT,                   -- JSON
    actor_type     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    prev_hash      TEXT NOT NULL,
    row_hash       TEXT NOT NULL
);
CREATE TRIGGER risk_assessments_no_update BEFORE UPDATE ON risk_assessments
BEGIN SELECT RAISE(ABORT, 'risk_assessments is append-only'); END;
CREATE TRIGGER risk_assessments_no_delete BEFORE DELETE ON risk_assessments
BEGIN SELECT RAISE(ABORT, 'risk_assessments is append-only'); END;

CREATE TABLE handoffs (
    seq            INTEGER PRIMARY KEY,
    id             TEXT NOT NULL UNIQUE,
    change_set_id  TEXT NOT NULL,
    from_role      TEXT NOT NULL,
    to_role        TEXT NOT NULL,
    verdict        TEXT,                   -- ACCEPT | REJECT (a REVIEWED judgment) or NULL
    domain         TEXT,
    payload        TEXT NOT NULL,          -- JSON, see roles/reference/handoff-schema.md
    actor_type     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    prev_hash      TEXT NOT NULL,
    row_hash       TEXT NOT NULL
);
CREATE TRIGGER handoffs_no_update BEFORE UPDATE ON handoffs
BEGIN SELECT RAISE(ABORT, 'handoffs is append-only'); END;
CREATE TRIGGER handoffs_no_delete BEFORE DELETE ON handoffs
BEGIN SELECT RAISE(ABORT, 'handoffs is append-only'); END;

CREATE TABLE forge_events (
    seq              INTEGER PRIMARY KEY,
    id               TEXT NOT NULL UNIQUE,
    change_set_id    TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    payload          TEXT NOT NULL,        -- JSON
    ingested_by      TEXT NOT NULL,
    resulting_status TEXT,
    timestamp        TEXT NOT NULL,
    prev_hash        TEXT NOT NULL,
    row_hash         TEXT NOT NULL
);
CREATE TRIGGER forge_events_no_update BEFORE UPDATE ON forge_events
BEGIN SELECT RAISE(ABORT, 'forge_events is append-only'); END;
CREATE TRIGGER forge_events_no_delete BEFORE DELETE ON forge_events
BEGIN SELECT RAISE(ABORT, 'forge_events is append-only'); END;
