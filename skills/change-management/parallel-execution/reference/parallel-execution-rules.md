# Parallel Execution Rules

## 1. Isolation
- One isolated **git worktree** per concurrently running task — not just one branch. Two tasks on
  different branches cannot safely share a checked-out working tree.
- Path convention: `/workspaces/<change-set-id>/<task-id>`; branch `<change-set-id>/<task-id>`.
- Each task's tool calls are confined to its worktree path.

## 2. Conflict detection
<!-- reconstructed: v2 source not provided; review -->
- **Before start:** compare planned file sets. Overlap, or both tasks touching an always-overlap
  path class (`../../snapshot/reference/staleness-policy.md`), → serialize via `depends_on`.
- **During:** after each checkpoint, compare the task's actual changed files with the other running
  tasks'. New overlap → pause the later-started task (`BLOCKED`), record a `RISK`, re-plan.
- **Scope check:** a task touching files outside its planned scope is a scope violation →
  `ESCALATE`, not retry (`grounding/agent-failure-modes`).

## 3. Partial completion
<!-- reconstructed: v2 source not provided; review -->
- A Change Set with some tasks `DONE` and others `FAILED`/`BLOCKED` does not integrate partially by
  default. Completed work stays on its branches with checkpoints.
- Integrating a subset requires a human decision recorded as a `DECISION`, and the Change Set is
  split (child Change Set with `parent_id`) so each integrates against its own completion criteria.

## 4. Merge ordering
<!-- reconstructed: v2 source not provided; review -->
- Merge in topological order of `depends_on`; ties: provider before consumer for contract changes,
  schema/migration before code that uses it.
- Contract changes follow expand → migrate → contract: backward-compatible provider change first,
  consumers next, removal of old behavior last.
- After each merge, later tasks rebase and re-verify on the new base (snapshot re-validation).

## 5. Operation classes

| Class | Meaning | Available to agents? | Resume-safe? |
|---|---|---|---|
| `READ` | Read files, run read-only commands | Yes | Yes |
| `WORKSPACE_WRITE` | Write within the task's worktree | Yes | Yes |
| `REPO_WRITE` | Commit/push to the task branch, open/update PR | Yes | Yes — verification precedes integration |
| `EXTERNAL_MUTATION` | Change state outside the repo (tickets, cloud resources, third-party APIs, databases) | **No** — CI/server only, on an observed authorized event | **No** |
| `DEPLOY` | Release to any environment | **No** — CI/server only, on an observed authorized event | **No** |

"Safe because it is on a branch and `VERIFYING` will catch it" holds for `REPO_WRITE`. It stops
holding the moment an operation crosses into `EXTERNAL_MUTATION` or `DEPLOY`.
