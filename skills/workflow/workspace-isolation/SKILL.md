---
name: workspace-isolation
description: Isolate IMPLEMENT/TEST/REVIEW work in git worktrees with deterministic naming, clean-main enforcement, and a 6-outcome handback protocol.
metadata:
  group: workflow
  phase: 2
  binding: false
  plan-ref: "§4.11"
  stage: IMPLEMENT
  inputs: [change-set]
  outputs: [worktree-path, delivery-branch]
  repo_roles: [app, tests]
---

# Workspace Isolation Protocol

## Purpose

Ensure that every implementation, test, and review stage operates in an isolated
git worktree so the main checkout stays clean and parallel work cannot interfere.
Worktrees are created with deterministic names and removed only through the
handback protocol.

## When this applies

- Before entering IMPLEMENT, TEST, or REVIEW for any Change Set.
- Whenever parallel execution spawns a worker (each worker gets its own worktree).
- During emergency stop (worktrees are preserved, not removed).

## Preflight

See [standard-preflight](../stage-preflight/reference/standard-preflight.md).

- **Inputs:** Change Set ID, target repository, current stage.
- **ADOPT:** verify main checkout is clean (`git status --porcelain` returns empty).
  If dirty, refuse to start and report BLOCKED with the list of dirty files.
- **Repo roles:** whatever the Change Set targets.

## Procedure

1. Verify main checkout is clean. If not, BLOCKED.
2. Create the worktree at the standard location:
   `../.wt/<project>/<change-set-id>` with `--no-track`.
3. Create a local-only branch: `wt/<change-set-id>` (never pushed).
4. Perform all work inside the worktree.
5. On completion, follow the [handback protocol](reference/handback-protocol.md).
6. Record the worktree lifecycle events to the event journal.

## Outputs

- `worktree_path`: absolute path to the created worktree.
- `delivery_branch`: the branch name following project conventions for PRs.
- Journal events: `task.start` (with worktree path), `task.deliver` or `task.abandon`.

## Enforcement

- **Stage preflight:** verifies main checkout is clean before worktree creation.
- **Hook:** prevents `git push` from local-only branches (prefix `wt/`).
- **CI check (target):** verify no orphaned worktrees older than 7 days.
- See [isolation-rules.md](reference/isolation-rules.md) for the full rule set.

## References

- [reference/isolation-rules.md](reference/isolation-rules.md)
- [reference/handback-protocol.md](reference/handback-protocol.md)
- [reference/branch-conventions.md](reference/branch-conventions.md)
- [Circuit Breaker](../../grounding/circuit-breaker/SKILL.md) — emergency stop preserves worktrees
- [Event Journal](../../mcp-servers/adlc-mcp/src/adlc_mcp/modules/event_journal/) — lifecycle events
