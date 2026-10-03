---
name: agent-failure-modes
description: Defines how agents detect and handle their own failures — loops, invalid output, scope violations, tool failures, context exhaustion, crashes, permission denials, security rejections — with a per-failure-class retry policy (RETRY / STOP / ESCALATE / REPLAN / RESUME). Use whenever an attempt fails or a task stalls.
metadata:
  group: grounding
  phase: 0
  binding: true
  plan-ref: "§4.1, §5.7"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Agent Failure Modes

## Purpose
Agents **will** fail. This skill defines the unhappy paths explicitly: iteration limits,
failure-class-specific retry policy, scope checks, and resumability.

## When this applies
On every failed attempt, rejected handoff, tool error, permission denial, or sign of context
pressure — and at the start of every run (to check for a prior partial run to resume).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the failing step's output, its failure class and the attempt count from the Change Set task checkpoint (if one exists).
- **ADOPT:** on resume, read prior ledger entries and the last checkpoint before retrying — RESUME, never restart blind.
- **BLOCK:** scope violations, permission denials and security rejections escalate immediately; they never consume the retry budget.
- **Repo roles:** none required beyond those of the stage that failed.

## Procedure
1. **At start of run:** query the ledger for prior entries on this task
   (`query_evidence` by `change_set_id` and task). If a checkpoint exists
   (`commit_sha`, `ledger_cursor`, `snapshot_id`), resume from it — do not regenerate from
   scratch.
2. **On failure:** classify it against
   [reference/failure-catalog.md](reference/failure-catalog.md) and apply that class's retry
   policy. Never apply a generic "try again".
3. **Only RETRY-class failures** draw from the per-task attempt budget (default 3). Scope
   violations, permission denials, and security rejections ESCALATE immediately and do **not**
   consume the budget.
4. **Before accepting any output**, run the scope check: does it touch files, APIs, or repos
   outside the Change Set scope? If yes, it is a scope violation — ESCALATE.
5. **Never silently skip a tool call** that failed. Transient → retry with backoff (1s, 4s, 16s);
   persistent → STOP and mark the task BLOCKED with the error as evidence.
6. **On context pressure** (approaching the context-decomposition threshold in
   `skill-routing/token-budget-optimizer/reference/context-budget.md`, default 60%): checkpoint
   to the ledger, then REPLAN the remainder into sub-tasks.
7. **On budget exhaustion:** set the task BLOCKED and write a summary entry listing each attempt,
   what changed between attempts, and the evidence of failure — formatted per
   `grounding/human-review-format`.
8. Record every failure as an entry (`classification: RISK` or `INFERENCE` for hypothesized
   cause) so `/self-improvement` can see it.

## Outputs
- Failure entries tagged with `failure_class` and `retry_policy`
- Checkpoint records (`commit_sha`, `ledger_cursor`, `snapshot_id`)
- BLOCKED summaries for human review

## Enforcement
- 3-attempt iteration cap: orchestrator-enforced counter, scoped by failure class (§5.6). In
  forge-native mode (Phase 1) the counter lives in the ledger, keyed by task.
- Permission denial: blocked at the tool-permission layer (managed settings / agent frontmatter)
  — the agent cannot retry its way past it.
- Scope check before acceptance and resume-before-regenerate: **guideline only** until the
  Change Management server (Phase 2) enforces scope on `record_handoff`.

## References
- [reference/failure-catalog.md](reference/failure-catalog.md)
- [../../change-management/change-set/reference/resumability-rules.md](../../change-management/change-set/reference/resumability-rules.md)
- [../../roles/reference/conflict-resolution.md](../../roles/reference/conflict-resolution.md)
- [../human-review-format/SKILL.md](../human-review-format/SKILL.md)
