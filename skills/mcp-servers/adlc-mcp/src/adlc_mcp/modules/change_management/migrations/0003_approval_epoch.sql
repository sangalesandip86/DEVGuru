-- Approval epoch: incremented on any scope change (tasks, requirements, repositories).
-- A PLAN_APPROVED from epoch N does not authorize epoch N+1 (ITIL normal-change authorization).
ALTER TABLE change_sets ADD COLUMN approval_epoch INTEGER NOT NULL DEFAULT 0;
