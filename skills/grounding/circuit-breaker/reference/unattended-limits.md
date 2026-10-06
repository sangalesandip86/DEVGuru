# Unattended Execution Limits

Default safety limits for autonomous/unattended execution. All limits are configurable
via environment variables or `.adlc/config.yaml`.

## Limits

| Limit | Default | Env Variable | Rationale |
|-------|---------|-------------|-----------|
| Max wall-clock time per task | 30 minutes | `ADLC_MAX_TASK_MINUTES` | Prevents runaway tasks from consuming resources indefinitely |
| Max task count per session | 20 | `ADLC_MAX_SESSION_TASKS` | Bounds total work per autonomous session |
| Max total token spend per session | 500K tokens | `ADLC_MAX_SESSION_TOKENS` | Cost guardrail for unattended LLM usage |

## Scope

These limits apply to:
- All background workers spawned by the Parallel Execution Coordinator
- Unattended loops (autonomous `/loop` sessions)
- Parallel execution children in isolated worktrees

## Enforcement

- **Circuit breaker** polls `.adlc/STOP` every 200ms — presence triggers immediate halt
- **PreToolUse hook** checks for `.adlc/STOP` before every tool invocation
- **Managed setting**: unattended execution requires circuit-breaker binding
- **CI check**: verify circuit-breaker is bound in all unattended workflow configurations

## Exceeded Behavior

When any limit is reached:

1. Current task is checkpointed (if checkpoint-capable)
2. `system.halt` event written to the Event Journal with reason and checkpoint data
3. `HALTED` evidence entry recorded in the Evidence Ledger
4. Worker stops gracefully — no partial writes left behind
5. Coordinator notified via coordination message

## Override

A human operator can raise limits for a specific session by setting the environment
variables. The circuit breaker's `.adlc/STOP` file always takes priority regardless
of configured limits.
