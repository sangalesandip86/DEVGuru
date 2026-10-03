-- ADR 0006: sanitized lessons, signal-only incidents, local evidence retention.

-- 1. Evidence retention by content commitment.
--    New entries keep a salted commitment (content_hash) inside the hash-chained row and put the
--    payload + salt in evidence_content, which is NOT chained. Retention deletes payload rows;
--    the chain still verifies (it never covered the payload), and the deleted content cannot be
--    recovered or brute-forced from the hash because the salt is deleted with it.
--    Entries written before this migration keep inline content (column `content`) and are exempt.
ALTER TABLE evidence ADD COLUMN content_hash TEXT;

CREATE TABLE evidence_content (
    entry_id    TEXT PRIMARY KEY REFERENCES evidence(entry_id),
    salt        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE ledger_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
INSERT INTO ledger_settings (key, value) VALUES ('evidence_retention_days', '90');

CREATE TRIGGER evidence_content_no_update BEFORE UPDATE ON evidence_content
BEGIN SELECT RAISE(ABORT, 'evidence_content is immutable'); END;

-- Payload may be deleted only once it is older than the retention period.
CREATE TRIGGER evidence_content_retention_guard BEFORE DELETE ON evidence_content
WHEN julianday(OLD.created_at) > julianday('now') -
     CAST((SELECT value FROM ledger_settings WHERE key = 'evidence_retention_days') AS REAL)
BEGIN SELECT RAISE(ABORT, 'evidence content is within its retention period'); END;

-- 2. Signal-only incidents. The v1 table carried free-text use-case fields; it is kept,
--    read-only and local, as incidents_v1 (its hash chain still verifies) and is never queried.
ALTER TABLE incidents RENAME TO incidents_v1;

CREATE TABLE incidents (
    seq                    INTEGER PRIMARY KEY,
    incident_id            TEXT NOT NULL UNIQUE,
    skill                  TEXT NOT NULL,
    step                   TEXT NOT NULL,
    failure_class          TEXT,
    signal_type            TEXT NOT NULL CHECK (signal_type IN
                             ('negative','positive','unverified-positive','efficiency','production')),
    signal_source          TEXT NOT NULL CHECK (signal_source IN ('AGENT','REVIEWER','HUMAN','PRODUCTION')),
    verification_strength  TEXT,          -- JSON {changed_code_coverage, acceptance_criteria_exercised}
    pattern_eligible       INTEGER NOT NULL CHECK (pattern_eligible IN (0, 1)),
    evidence_refs          TEXT NOT NULL, -- JSON array of entry_ids in this ledger (pointers only)
    note                   TEXT CHECK (note IS NULL OR length(note) <= 280),
    note_author_type       TEXT,
    note_author_id         TEXT,
    actor_type             TEXT NOT NULL,
    actor_id               TEXT NOT NULL,
    agent_role             TEXT,
    platform_release_sha   TEXT NOT NULL,
    timestamp              TEXT NOT NULL,
    prev_hash              TEXT NOT NULL,
    row_hash               TEXT NOT NULL
);
CREATE INDEX incidents_cluster ON incidents (skill, step, failure_class);
CREATE TRIGGER incidents_v2_no_update BEFORE UPDATE ON incidents
BEGIN SELECT RAISE(ABORT, 'incidents is append-only'); END;
CREATE TRIGGER incidents_v2_no_delete BEFORE DELETE ON incidents
BEGIN SELECT RAISE(ABORT, 'incidents is append-only'); END;

-- 3. Lessons (ADR 0006 §2). A promotion to ORG scope is a new row pointing at the PROJECT lesson.
CREATE TABLE lessons (
    seq                  INTEGER PRIMARY KEY,
    lesson_id            TEXT NOT NULL UNIQUE,
    parent_lesson_id     TEXT REFERENCES lessons(lesson_id),
    skill                TEXT NOT NULL,
    step                 TEXT NOT NULL,
    failure_class        TEXT NOT NULL,
    occurrences          TEXT NOT NULL,   -- JSON {incidents, change_sets, projects}
    what_failed          TEXT NOT NULL CHECK (length(what_failed) <= 280),
    advice               TEXT NOT NULL CHECK (length(advice) <= 500),
    "check"              TEXT,
    remedy_kind          TEXT NOT NULL CHECK (remedy_kind IN ('GATE','LINT','SKILL_TEXT','EXAMPLE')),
    reproduction_ref     TEXT,            -- synthetic evals.json case (never the real case)
    incident_refs        TEXT NOT NULL,   -- JSON array of local incident_ids (stay in project scope)
    sanitization_result  TEXT NOT NULL,   -- JSON {passed: true, checker_version, checked_at}
    scope                TEXT NOT NULL CHECK (scope IN ('PROJECT','ORG')),
    approval_entry_id    TEXT,            -- HUMAN APPROVED evidence entry (required for ORG)
    actor_type           TEXT NOT NULL,
    actor_id             TEXT NOT NULL,
    agent_role           TEXT,
    platform_release_sha TEXT NOT NULL,
    timestamp            TEXT NOT NULL,
    prev_hash            TEXT NOT NULL,
    row_hash             TEXT NOT NULL
);
CREATE TRIGGER lessons_no_update BEFORE UPDATE ON lessons
BEGIN SELECT RAISE(ABORT, 'lessons is append-only'); END;
CREATE TRIGGER lessons_no_delete BEFORE DELETE ON lessons
BEGIN SELECT RAISE(ABORT, 'lessons is append-only'); END;
