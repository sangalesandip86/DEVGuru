# Resumability Rules

<!-- reconstructed: v2 source not provided; review -->

## Resume procedure
1. Read the task's `checkpoint` (`commit_sha`, `ledger_cursor`, `snapshot_id`).
2. Read all ledger entries for the Change Set after `ledger_cursor` (`query_evidence`) — partial-run
   entries persist across crashes (`grounding/agent-failure-modes`, retry policy `RESUME`).
3. Check out the task's worktree at `commit_sha`. If the worktree is missing, recreate it from the
   branch; if the branch head differs from `commit_sha`, treat the newer commits as unverified work
   to review, not as trusted progress.
4. Run `validate_snapshot_currency`. If stale, re-run affected analysis before continuing.
5. Re-load the routed skill set recorded in the routing `DECISION` entry — never a smaller set.
6. Continue from the first incomplete step; do not regenerate completed, checkpointed work.

## Safety scope — operation classes
The reasoning "it's safe to re-run because it's on a branch and `VERIFYING` will catch it" applies
**only** to `READ`, `WORKSPACE_WRITE`, and `REPO_WRITE`-on-a-branch operations.

| Operation class | Safe to replay on resume? |
|---|---|
| `READ` | Yes |
| `WORKSPACE_WRITE` | Yes — worktree is disposable |
| `REPO_WRITE` (branch) | Yes — verification precedes integration |
| `EXTERNAL_MUTATION` | **No** — not undoable by later verification; never available to agents |
| `DEPLOY` | **No** — never available to agents |

If ledger evidence shows an `EXTERNAL_MUTATION` or `DEPLOY` occurred during the interrupted run
(by CI/server), resumption must not repeat it; the task goes `BLOCKED` pending human review of the
external state.

## Attempts
Resuming after a crash does not consume an attempt. A resume that re-fails for the same reason does.
