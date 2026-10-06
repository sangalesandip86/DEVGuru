# ADLC Workspace Layout

The `.adlc/` directory holds a project's local platform state.

```
.adlc/
├── STOP            # circuit-breaker halt file (presence = halt)
├── db/             # local databases (ledger index, caches of record)
├── journal/        # evidence journal, incl. HALTED events
├── internal/       # INTERNAL-visibility documents
├── handoffs/       # recorded handoffs
├── decisions.md    # DECISION log / short ADRs
├── locks/          # lock files for concurrent sessions
├── lessons/        # captured lessons (self-improvement)
├── cache/          # regenerable caches
├── worktrees.json  # registry of task worktrees
└── logs/           # run logs
```

| Path | Purpose |
|---|---|
| `STOP` | See `skills/grounding/circuit-breaker`; created and removed by a human |
| `internal/` | Documents with `INTERNAL` visibility (see evidence-ledger, Visibility) |
| `cache/` | Safe to delete; rebuilt on demand |

## Location
- Default: `.adlc/` at the project root.
- Override with the `ADLC_WORKSPACE_ROOT` environment variable.

## Gitignore
`.adlc/` is automatically added to `.gitignore`; it is never committed.

## Open question
Per-project vs. user-level workspace. **Current default: per-project.** Unresolved; revisit
before multi-project sessions are supported.
