---
name: parallel-execution
description: Run multiple tasks concurrently with isolated worktrees and conflict detection. Use when more than one task runs at the same time.
metadata:
  group: change-management
  phase: 2
  binding: true
  plan-ref: "§4.5"
  stage: IMPLEMENT
  inputs: [change-set]
  outputs: []
  repo_roles: [app]
---

# Parallel Execution

## Purpose
Let independent tasks run concurrently without corrupting each other's working state or merging in
an unsafe order.

## When this applies
A Change Set has two or more tasks whose `depends_on` are satisfied at the same time.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Applies only when a Change Set has more than one concurrently runnable task.

- **Inputs:** the Change Set's `tasks[]` with dependencies and checkpoints.
- **ADOPT:** existing worktrees for a task are reused only if their checkpoint SHA matches; otherwise a fresh worktree is created (WORKSPACE_WRITE).
- **Repo roles:** `app` (one isolated worktree per running task).

## Procedure
1. Give each running task its **own git worktree** (`git worktree add <path> -b <branch>`), recorded
   in `tasks[].worktree`. Two tasks never share one checked-out tree, even on different branches.
2. Before starting, predict file overlap between concurrent tasks. Predicted overlap → serialize them
   (add a `depends_on` edge) instead of running in parallel.
3. Follow [parallel-execution-rules.md](reference/parallel-execution-rules.md) for conflict detection,
   partial completion, and merge ordering.
4. Use only agent operation classes (`READ`, `WORKSPACE_WRITE`, `REPO_WRITE`). `EXTERNAL_MUTATION`
   and `DEPLOY` belong to CI and the server.
5. Remove worktrees when a task is `DONE` and merged, or `CANCELLED`.

## Outputs
- `tasks[].worktree`, `tasks[].branch`, checkpoints per task.
- `RISK` entry on any detected conflict; `DECISION` entry for merge order.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.

- Operation classes: agent credentials and tool scoping expose no deploy or external-mutation tool
  (§5.6; `governance/default-permissions`).
- Worktree isolation: orchestrator-enforced when it spawns tasks; guideline only otherwise.

## References
- [reference/parallel-execution-rules.md](reference/parallel-execution-rules.md)
- [../change-set/reference/tasks-and-checkpoints.md](../change-set/reference/tasks-and-checkpoints.md)
- [../change-set/reference/resumability-rules.md](../change-set/reference/resumability-rules.md)
