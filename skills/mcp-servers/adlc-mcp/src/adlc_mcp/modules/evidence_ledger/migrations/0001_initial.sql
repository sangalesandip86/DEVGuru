-- Evidence Ledger (plan §4.3 ledger-entry-schema). Append-only and hash-chained.
CREATE TABLE evidence (
    seq                  INTEGER PRIMARY KEY,
    entry_id             TEXT NOT NULL UNIQUE,
    run_id               TEXT NOT NULL,
    change_set_id        TEXT,
    actor_type           TEXT NOT NULL CHECK (actor_type IN ('HUMAN','AGENT','SYSTEM')),
    actor_id             TEXT NOT NULL,
    agent_role           TEXT,
    model_id             TEXT,
    tool                 TEXT NOT NULL,
    classification       TEXT NOT NULL CHECK (classification IN
                           ('FACT','INFERENCE','ASSUMPTION','PROPOSAL','QUESTION','DECISION','RISK')),
    trust_level          TEXT NOT NULL CHECK (trust_level IN
                           ('SYSTEM','ORGANIZATIONAL','REPOSITORY','EXTERNAL_STRUCTURED','EXTERNAL_UNSTRUCTURED')),
    source_type          TEXT NOT NULL,
    content              TEXT NOT NULL,
    source               TEXT,
    input_references     TEXT,   -- JSON array of entry_ids
    output_references    TEXT,   -- JSON array
    decision_ids         TEXT,   -- JSON array
    lifecycle_state      TEXT CHECK (lifecycle_state IS NULL OR lifecycle_state IN
                           ('DRAFT','PROPOSED','REVIEWED','VERIFIED','APPROVED','REJECTED')),
    snapshot_id          TEXT,
    parent_entry_id      TEXT REFERENCES evidence(entry_id),
    outcome_status       TEXT,   -- CHALLENGED (correction) | ANSWERED (answer to a QUESTION)
    platform_release_sha TEXT NOT NULL,
    timestamp            TEXT NOT NULL,
    signal_source        TEXT CHECK (signal_source IS NULL OR signal_source IN ('AGENT','REVIEWER','HUMAN','PRODUCTION')),
    metadata             TEXT,   -- JSON: QUESTION {blocking}, ASSUMPTION {impact, expires_at}, ...
    prev_hash            TEXT NOT NULL,
    row_hash             TEXT NOT NULL
);
CREATE INDEX evidence_change_set ON evidence (change_set_id);
CREATE INDEX evidence_parent ON evidence (parent_entry_id);

CREATE TRIGGER evidence_no_update BEFORE UPDATE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;

-- Self-improvement incidents (plan §4.2) — "another table in the same Evidence Ledger".
-- Status progresses by appending a new row with parent_incident_id, never by editing.
CREATE TABLE incidents (
    seq                  INTEGER PRIMARY KEY,
    incident_id          TEXT NOT NULL UNIQUE,
    parent_incident_id   TEXT REFERENCES incidents(incident_id),
    skill                TEXT NOT NULL,
    pattern              TEXT,
    signal_type          TEXT NOT NULL CHECK (signal_type IN ('negative','positive','efficiency','production')),
    signal_source        TEXT NOT NULL CHECK (signal_source IN ('AGENT','REVIEWER','HUMAN','PRODUCTION')),
    verification_tag     TEXT,   -- verified-positive | unverified-positive (positive signals only)
    trigger              TEXT NOT NULL,
    context              TEXT,   -- JSON
    hypothesis           TEXT,   -- always an INFERENCE, explicitly unconfirmed
    proposal             TEXT,
    status               TEXT NOT NULL CHECK (status IN ('OPEN','REVIEWED','APPROVED','REJECTED')),
    change_set_id        TEXT,
    related_entry_ids    TEXT,   -- JSON array of evidence entry_ids
    actor_type           TEXT NOT NULL,
    actor_id             TEXT NOT NULL,
    agent_role           TEXT,
    platform_release_sha TEXT NOT NULL,
    timestamp            TEXT NOT NULL,
    prev_hash            TEXT NOT NULL,
    row_hash             TEXT NOT NULL
);
CREATE INDEX incidents_skill ON incidents (skill);

CREATE TRIGGER incidents_no_update BEFORE UPDATE ON incidents
BEGIN SELECT RAISE(ABORT, 'incidents is append-only'); END;
CREATE TRIGGER incidents_no_delete BEFORE DELETE ON incidents
BEGIN SELECT RAISE(ABORT, 'incidents is append-only'); END;
