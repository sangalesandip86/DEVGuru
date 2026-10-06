# Handback Protocol

Six possible outcomes when a worktree completes (or fails to complete) its work.
Every outcome has a deterministic procedure — no ambiguity about what to do.

## Outcomes

| # | Outcome | Procedure | Worktree Fate |
|---|---------|-----------|---------------|
| 1 | **Delivery success** | Push delivery branch → open PR → record `task.deliver` → remove worktree | Removed |
| 2 | **Local work success** | List modified files → three-way merge to main → leave unstaged → remove worktree | Removed |
| 3 | **Push/PR failure** | Preserve worktree → report exact path → record BLOCKED with error details | Preserved |
| 4 | **Dirty main checkout** | Refuse to start → report BLOCKED with list of dirty files | Not created |
| 5 | **Merge conflict** | Halt → list conflicting files → preserve worktree → ESCALATE to human | Preserved |
| 6 | **Emergency stop** | Preserve worktree → checkpoint progress to event journal → halt immediately | Preserved |

## Detailed procedures

### 1. Delivery success

The normal path for shipping work:

1. Create the delivery branch following project conventions (e.g., `feature/<ticket>-<slug>`).
2. Push the delivery branch to the remote.
3. Open a PR with the standard body (`Implements: ST-<n>`).
4. Record a `task.deliver` event in the event journal with the PR URL.
5. Remove the worktree: `git worktree remove <path>`.
6. Delete the local-only branch: `git branch -d wt/<change-set-id>`.

### 2. Local work success

For work that does not ship directly (e.g., intermediate integration):

1. List all modified files in the worktree.
2. Check out the main branch.
3. Perform a three-way merge from the worktree branch into main.
4. Leave changes unstaged (do not commit — the coordinator or human decides).
5. Remove the worktree: `git worktree remove <path>`.
6. Delete the local-only branch.

### 3. Push/PR failure

When the remote rejects the push or PR creation fails:

1. Do NOT remove the worktree.
2. Record a BLOCKED event with the exact error message.
3. Report the worktree path so the human can investigate.
4. If the failure is transient (network), retry once after 30 seconds.
5. If the failure is persistent (permission, branch protection), ESCALATE.

### 4. Dirty main checkout

The pre-condition check fails:

1. Run `git status --porcelain` on the main checkout.
2. If non-empty, report BLOCKED with the full file list.
3. Do NOT create a worktree.
4. Do NOT attempt to clean the main checkout (stash, reset, etc.).
5. The human must resolve the dirty state before work can begin.

### 5. Merge conflict

When merging worktree changes back to main produces conflicts:

1. Halt the merge immediately.
2. List all conflicting files with their conflict markers.
3. Preserve the worktree (do not remove it).
4. Record an ESCALATE event with the conflict details.
5. The human resolves conflicts manually, then signals completion.

### 6. Emergency stop

When the circuit breaker triggers (`.adlc/STOP` detected):

1. Stop all work immediately — do not attempt to complete the current operation.
2. Checkpoint current progress to the event journal:
   - Current commit SHA in the worktree.
   - List of modified files.
   - Last completed step in the procedure.
3. Preserve the worktree intact.
4. Record a `system.halt` event with checkpoint data.
5. After `.adlc/STOP` is removed, work can resume from the checkpoint.
