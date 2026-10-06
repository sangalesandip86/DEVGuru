# Isolation Rules

Rules governing worktree creation, naming, and lifecycle for IMPLEMENT, TEST,
and REVIEW stages.

## Worktree location

All worktrees are created at a standard, predictable location outside the main
checkout:

```
../.wt/<project-name>/<change-set-id>/
```

- `<project-name>` is the repository directory name.
- `<change-set-id>` is the Change Set identifier (e.g., `CS-042`).
- The `../.wt/` prefix keeps worktrees outside the main checkout's tree,
  preventing accidental inclusion in diffs or glob scans.

## Branch naming

| Branch Type | Pattern | Purpose |
|------------|---------|---------|
| Local-only (work) | `wt/<change-set-id>` | Temporary work branch; never pushed |
| Delivery | `feature/<ticket>-<slug>` | Follows project convention; pushed for PR |

- The local-only branch is created with `--no-track` to prevent accidental
  upstream tracking.
- The delivery branch name is discovered from the project's conventions catalog
  (`.adlc/catalog/conventions.json`), falling back to `feature/<ticket>-<slug>`.

## Creation rules

1. **Main checkout must be clean.** `git status --porcelain` must return empty.
   If dirty files exist, report BLOCKED with the file list. Never force-clean
   the main checkout.
2. **One worktree per Change Set per stage.** Creating a second worktree for the
   same Change Set while one exists is an error — resume the existing one.
3. **Use `--no-track`.** Prevents the local branch from tracking a remote branch.
   ```
   git worktree add --no-track -b wt/<change-set-id> ../.wt/<project>/<change-set-id>
   ```
4. **Record creation** in the event journal with a `task.start` event including
   the worktree absolute path.

## Lifecycle

```
main checkout (clean)
  ↓ git worktree add --no-track
worktree created at ../.wt/<project>/<CS-id>
  ↓ work happens here
handback protocol determines outcome
  ↓ on success: worktree removed
  ↓ on failure: worktree preserved
```

## Cleanup

- Successful handback: `git worktree remove ../.wt/<project>/<change-set-id>`.
- Failed handback: preserve the worktree and report its path.
- Emergency stop: preserve the worktree and checkpoint to the event journal.
- Orphan detection: CI check flags worktrees older than 7 days.
