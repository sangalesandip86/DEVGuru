# Worker Sandbox Policy

Restrictions applied to every worker spawned by the Parallel Execution
Coordinator. Workers operate in a restricted subset of the parent role's
permissions to prevent accidental or malicious side effects.

## Environment allowlist

Workers inherit only these 12 environment variables. All others are stripped
before the worker process starts.

| # | Variable | Purpose |
|---|----------|---------|
| 1 | `HOME` | Home directory (required by git and many tools) |
| 2 | `PATH` | Executable search path |
| 3 | `LANG` | Locale (prevents encoding errors) |
| 4 | `TERM` | Terminal type (for tool output formatting) |
| 5 | `EDITOR` | Default editor (for git commit, if needed) |
| 6 | `ADLC_SKILLS_ROOT` | Skills directory for cross-project portability |
| 7 | `ADLC_CHANGE_SET_ID` | The Change Set this worker belongs to |
| 8 | `ADLC_WORKER_ID` | Unique worker identifier (for journal entries) |
| 9 | `ADLC_RISK_TIER` | Risk tier of the Change Set |
| 10 | `GIT_AUTHOR_NAME` | Git authorship (consistent across workers) |
| 11 | `GIT_AUTHOR_EMAIL` | Git authorship email |
| 12 | `GIT_COMMITTER_NAME` | Git committer name |

## Credential isolation

- **No coordinator credentials.** Workers do not receive the coordinator's
  bearer token, API keys, or session tokens.
- **No MCP server token.** Workers authenticate independently with a
  worker-scoped identity derived from `ADLC_WORKER_ID`.
- **No forge tokens.** Workers cannot push, open PRs, or interact with GitHub/
  GitLab APIs. Only the coordinator has forge access.

## Git command restrictions

### Allowed commands (read-only)

Workers may execute only these exact git commands:

```
git status
git diff
git diff --staged
git log --oneline -20
```

No trailing arguments are allowed — the commands must match exactly. This
prevents argument injection (e.g., `git diff -- --output=/etc/passwd`).

### Denied command patterns

Any git command matching this pattern is blocked:

```regex
^git\s+(push|force|reset|rebase|merge|checkout\s+(-b|--orphan))
```

This blocks:
- `git push` (any form)
- `git force` (any form)
- `git reset` (any form)
- `git rebase` (any form)
- `git merge` (any form)
- `git checkout -b` and `git checkout --orphan` (branch creation)

### Commit restrictions

Workers **can** commit to their local worktree branch (needed for incremental
work). They **cannot** push those commits. The coordinator collects results by
reading the worktree's branch after the worker completes.

## Network restrictions

- **No external network access.** Workers cannot call external APIs, download
  packages, or make HTTP requests.
- **Local MCP server only.** Workers communicate only with the local MCP server
  on 127.0.0.1.
- **No outbound connections.** Enforced by the worker's managed settings, which
  deny network-capable tools.

## Tool restrictions by role

Workers inherit their parent role's tool permissions with additional
restrictions:

| Tool Category | Worker Access |
|--------------|--------------|
| Read tools (Read, Grep, Glob) | Allowed |
| Write/Edit tools | Allowed for developer, test-engineer roles only |
| Bash | Limited to discovered CI/test commands + 4 read-only git commands |
| MCP tools | Role-filtered (same as parent) minus forge-interaction tools |
| Commit | Allowed (local only) |
| Push/PR | Denied |
| Approve gates | Denied |
| Set status | Denied |

## Emergency stop

When the circuit breaker triggers (`.adlc/STOP` detected):

1. All workers halt within 1 second.
2. Each worker preserves its worktree.
3. Each worker writes a `system.halt` event to the journal.
4. The coordinator collects halt status from all workers.
5. No cleanup is performed — worktrees and local branches are preserved.
