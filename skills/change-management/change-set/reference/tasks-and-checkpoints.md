# Tasks and Checkpoints

`tasks[]` is embedded directly in the Change Set record, so lifecycle, parallel-execution, and
resumability rules have a schema to act on.

```yaml
tasks:
  - id: TASK-14
    title: "Add cross-border fee to refund calculator"
    repo: acme/billing
    depends_on: [TASK-12]
    owner_role: developer
    ac_refs: [ST-101/AC-1, ST-101/AC-3]   # acceptance criteria this task implements (v3.1 §4.12)
    worktree: /workspaces/CS-881/task-14
    branch: cs-881/task-14
    status: CHECKPOINTED        # PENDING | RUNNING | CHECKPOINTED | DONE | BLOCKED | FAILED
    attempts: 1                 # counts RETRY-class failures only; cap 3
    operation_classes: [READ, WORKSPACE_WRITE, REPO_WRITE]
    checkpoint:
      commit_sha: a1b2c3d
      ledger_cursor: ENTRY-9981
      snapshot_id: SNAP-220
      timestamp: "2026-10-03T11:20:00Z"
```

## Rules
- `ac_refs` lists the story acceptance criteria (`ST-<n>/AC-<n>`) the task implements. Every
  AC of every story in the Change Set's `story_refs[]` should be covered by at least one task;
  an uncovered AC is a planning gap (`QUESTION`), not something to infer.
- `depends_on` forms a DAG; a cycle is a planning error (`BLOCKED`).
- A task starts only when every `depends_on` task is `DONE`.
- `attempts` increments only on `RETRY`-class failures. `ESCALATE` failures (scope violation,
  permission denial, security rejection) never draw from it (`grounding/agent-failure-modes`).
- Write a checkpoint: after each commit, before any handoff, and when context use crosses the
  decomposition threshold (`skill-routing/token-budget-optimizer`).
- `ledger_cursor` is the last ledger `entry_id` the task had seen; resume reads everything after it.
- Concurrent tasks each get their own `worktree` (`../../parallel-execution/SKILL.md`).
- `operation_classes` lists what the task may do; `EXTERNAL_MUTATION` and `DEPLOY` are invalid
  values for any agent-owned task.
