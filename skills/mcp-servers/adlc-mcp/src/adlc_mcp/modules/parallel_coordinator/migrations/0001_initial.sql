CREATE TABLE IF NOT EXISTS parallel_plans (
    plan_id         TEXT PRIMARY KEY,
    change_set_id   TEXT NOT NULL,
    max_workers     INTEGER NOT NULL DEFAULT 8,
    auto_start      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_cs ON parallel_plans(change_set_id);

CREATE TABLE IF NOT EXISTS work_items (
    item_id         TEXT PRIMARY KEY,
    plan_id         TEXT NOT NULL REFERENCES parallel_plans(plan_id),
    change_set_id   TEXT NOT NULL,
    description     TEXT NOT NULL,
    planned_files   TEXT NOT NULL DEFAULT '[]',
    role            TEXT NOT NULL DEFAULT 'developer',
    state           TEXT NOT NULL DEFAULT 'pending',
    worker_id       TEXT NOT NULL DEFAULT '',
    worktree_path   TEXT NOT NULL DEFAULT '',
    result          TEXT NOT NULL DEFAULT '{}',
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_plan ON work_items(plan_id);
CREATE INDEX IF NOT EXISTS idx_items_state ON work_items(state);
