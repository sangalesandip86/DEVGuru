-- Expand contract types: add graphql, module, websocket.
-- SQLite requires table recreation to alter a CHECK constraint.
CREATE TABLE contracts_new (
    contract_id          TEXT PRIMARY KEY,
    provider             TEXT NOT NULL,
    consumers            TEXT NOT NULL,
    type                 TEXT NOT NULL CHECK (type IN ('http','grpc','event','schema','graphql','module','websocket')),
    compatibility_policy TEXT NOT NULL CHECK (compatibility_policy IN ('BACKWARD','FORWARD','FULL','NONE')),
    registered_by        TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
INSERT INTO contracts_new SELECT * FROM contracts;
DROP TABLE contracts;
ALTER TABLE contracts_new RENAME TO contracts;
