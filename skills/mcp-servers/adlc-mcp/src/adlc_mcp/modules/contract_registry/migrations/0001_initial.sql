-- Contract Registry (plan §4.6, §6 Server 3). Own database file; no shared tables.
CREATE TABLE contracts (
    contract_id          TEXT PRIMARY KEY,
    provider             TEXT NOT NULL,
    consumers            TEXT NOT NULL,          -- JSON array of app names
    type                 TEXT NOT NULL CHECK (type IN ('http','grpc','event','schema')),
    compatibility_policy TEXT NOT NULL CHECK (compatibility_policy IN ('BACKWARD','FORWARD','FULL','NONE')),
    registered_by        TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE contract_versions (
    contract_id   TEXT NOT NULL REFERENCES contracts(contract_id),
    version       TEXT NOT NULL,
    party         TEXT NOT NULL,                 -- provider app or a consumer app (each declares its view)
    spec          TEXT NOT NULL,                 -- JSON
    registered_by TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (contract_id, version, party)
);
CREATE TRIGGER contract_versions_no_update BEFORE UPDATE ON contract_versions
BEGIN SELECT RAISE(ABORT, 'contract versions are immutable; register a new version'); END;
CREATE TRIGGER contract_versions_no_delete BEFORE DELETE ON contract_versions
BEGIN SELECT RAISE(ABORT, 'contract versions are immutable'); END;

-- Fed by CI (SYSTEM). The data check_compatibility checks against (never "latest vs latest").
CREATE TABLE deployments (
    seq               INTEGER PRIMARY KEY,
    app               TEXT NOT NULL,
    version           TEXT NOT NULL,
    environment       TEXT NOT NULL,
    contract_versions TEXT NOT NULL,             -- JSON {contract_id: version}
    recorded_by       TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    prev_hash         TEXT NOT NULL,
    row_hash          TEXT NOT NULL
);
CREATE INDEX deployments_env_app ON deployments (environment, app);
CREATE TRIGGER deployments_no_update BEFORE UPDATE ON deployments
BEGIN SELECT RAISE(ABORT, 'deployments is append-only'); END;
CREATE TRIGGER deployments_no_delete BEFORE DELETE ON deployments
BEGIN SELECT RAISE(ABORT, 'deployments is append-only'); END;

CREATE TABLE check_results (
    seq          INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,                  -- compatibility | drift
    contract_id  TEXT NOT NULL,
    request      TEXT NOT NULL,                  -- JSON
    result       TEXT NOT NULL,                  -- JSON
    actor_type   TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    row_hash     TEXT NOT NULL
);
CREATE TRIGGER check_results_no_update BEFORE UPDATE ON check_results
BEGIN SELECT RAISE(ABORT, 'check_results is append-only'); END;
CREATE TRIGGER check_results_no_delete BEFORE DELETE ON check_results
BEGIN SELECT RAISE(ABORT, 'check_results is append-only'); END;
