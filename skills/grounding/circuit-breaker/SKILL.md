---
name: circuit-breaker
description: Emergency halt for autonomous or unattended execution via a .adlc/STOP file plus session limits. Use before every tool invocation and when running unattended.
metadata:
  group: grounding
  phase: 0
  binding: true
  plan-ref: "§4.1, §5.9"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Circuit Breaker

## Purpose
An emergency halt mechanism for autonomous / unattended execution. A human can stop all work
by creating one file; session limits stop runaway runs without a human.

## When this applies
Always, and in particular in unattended or background execution (including background workers).

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md) (cross-cutting).

- **Inputs:** the workspace root (see `docs/workspace-layout.md`) and the configured session limits.
- **BLOCK:** if `.adlc/STOP` exists at session start, do not begin; report the halt.
- **Repo roles:** none.

## Procedure
1. **Before every tool invocation**, check for `.adlc/STOP` in the workspace root. If present,
   halt immediately — do not start the tool call.
2. On halt, in order:
   1. Write a `HALTED` event to the evidence journal.
   2. Checkpoint current progress to the ledger.
   3. Preserve the workspace (no cleanup, no reset, no worktree removal).
   4. Report the halt, naming the checkpoint entry and any in-flight work.
3. **Resume:** a human removes `.adlc/STOP`; execution resumes from the last checkpoint
   (`grounding/agent-failure-modes`, RESUME). Never remove the STOP file yourself.
4. Track session limits and halt the same way when one is reached (defaults; see
   [reference/stop-protocol.md](reference/stop-protocol.md)):
   - max wall-clock: 30 minutes
   - max tasks per session: 20
   - max tokens per session: 500K

## Outputs
- `HALTED` journal event and a checkpoint ledger entry
- A halt report naming the trigger (STOP file or limit)

## Enforcement
**Guideline** with hook support — the STOP check is designed to run in a `PreToolUse` hook; where
that hook is not installed, this skill is guidance only.

| Rule | Enforced by |
|---|---|
| STOP file halts tool use | `PreToolUse` hook (where installed); otherwise guideline only |
| Session limits | Guideline only unless the host enforces them |

## References
- [reference/stop-protocol.md](reference/stop-protocol.md)
- [../agent-failure-modes/SKILL.md](../agent-failure-modes/SKILL.md)
- [../../../docs/workspace-layout.md](../../../docs/workspace-layout.md)
