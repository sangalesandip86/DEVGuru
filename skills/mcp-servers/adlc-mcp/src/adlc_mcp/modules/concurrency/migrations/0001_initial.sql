CREATE TABLE IF NOT EXISTS task_claims (
    task_id     TEXT PRIMARY KEY,
    actor_id    TEXT NOT NULL,
    claimed_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_intents (
    intent_id     TEXT PRIMARY KEY,
    actor_id      TEXT NOT NULL,
    agent_role    TEXT NOT NULL DEFAULT '',
    files         TEXT NOT NULL DEFAULT '[]',
    declared_at   TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    change_set_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_intents_actor ON file_intents(actor_id);
CREATE INDEX IF NOT EXISTS idx_intents_cs ON file_intents(change_set_id);

CREATE TABLE IF NOT EXISTS coord_messages (
    message_id    TEXT PRIMARY KEY,
    from_actor    TEXT NOT NULL,
    from_role     TEXT NOT NULL DEFAULT '',
    to_actor      TEXT NOT NULL,
    content       TEXT NOT NULL,
    sent_at       TEXT NOT NULL,
    change_set_id TEXT NOT NULL DEFAULT '',
    intent_id     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_messages_to ON coord_messages(to_actor);
