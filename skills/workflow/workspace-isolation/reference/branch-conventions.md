# Branch Conventions

Naming rules for branches created during workspace isolation.

## Two branch types

| Type | Pattern | Pushed? | Purpose |
|------|---------|---------|---------|
| **Local-only** | `wt/<change-set-id>` | Never | Temporary work branch inside the worktree |
| **Delivery** | Follows project convention | Yes | Branch that becomes the PR |

## Local-only branches

- Created automatically with the worktree via `git worktree add --no-track -b wt/<CS-id>`.
- Prefix `wt/` signals "worktree-local" — hooks prevent pushing branches with this prefix.
- Deleted after successful handback.
- If the worktree is preserved (failure, emergency stop), the branch is also preserved.

## Delivery branches

The delivery branch name comes from the project's conventions catalog. Discovery
order:

1. `.adlc/catalog/conventions.json` → `branch_naming.feature` pattern.
2. Repository `CONTRIBUTING.md` or `AGENTS.md` branch naming section.
3. Observed pattern from recent feature branches (`git branch -r --list 'origin/feature/*'`).
4. Fallback: `feature/<ticket-id>-<slug>` (e.g., `feature/ST-042-add-payment-retry`).

### Slug rules

- Derived from the story title, lowercased, spaces replaced with hyphens.
- Max 50 characters (truncated, not wrapped).
- Only `[a-z0-9-]` characters; other characters stripped.

## Single-repo conventions

For Change Sets targeting a single repository:

```
wt/CS-042                          # local-only work branch
feature/ST-101-add-retry-logic     # delivery branch
```

## Multi-repo conventions

For Change Sets spanning multiple repositories, each repo gets its own worktree
and branch pair:

```
# Repo: api-service
../.wt/api-service/CS-042/
  branch: wt/CS-042
  delivery: feature/ST-101-add-retry-logic

# Repo: shared-lib
../.wt/shared-lib/CS-042/
  branch: wt/CS-042
  delivery: feature/ST-102-update-retry-types
```

- Each repo's delivery branch references its own story ID.
- The Change Set ID is shared across all worktrees.
- Multi-repo parallel execution requires human approval (per the parallel
  execution coordinator's automatic start conditions).
