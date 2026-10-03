---
name: human-review-format
description: Formats anything presented to a human for a decision — approval summaries, escalations, BLOCKED reports, conflicting reviews — so the decision, evidence, risk, and open questions are scannable and every claim is sourced. Use whenever output will be read by a human approver or escalation target.
metadata:
  group: grounding
  phase: 0
  binding: true
  plan-ref: "§4.1"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

<!-- reconstructed: v2 source not provided; review -->

# Human Review Format

## Purpose
Human attention is the scarcest resource in the platform and the only source of `APPROVED`.
Present decisions so a reviewer can decide quickly **and** correctly — without having to trust
agent prose they cannot verify.

## When this applies
- Approval requests (per `change-management/change-set/reference/approval-matrix.md`)
- Escalations (scope violation, permission denial, security REJECT, cross-domain conflict)
- BLOCKED summaries after an exhausted attempt budget
- Degraded Mode routing to a named human standing in for an unbuilt role
- Self-improvement candidate revisions awaiting `APPROVED`

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the evidence package being put in front of a human (approval request, escalation, QUESTION batch).
- **BACKFILL:** if the package is missing VERIFIED evidence the tier requires, say so explicitly rather than presenting it as complete.
- **Repo roles:** none required; links in the package are pinned `repo@sha:path` references.

## Procedure
1. Lead with **the decision being asked for**, in one sentence, and who is being asked
   (`human:tech-lead`, etc.).
2. State the **risk tier** and why (path match, reason code, escalation history).
3. Show **authority status** separately and never blur them: what is `VERIFIED` (machine
   evidence), what is `REVIEWED` (agent judgment), what is still unverified.
4. List **open blocking QUESTIONs** and **unexpired ASSUMPTIONs with impact > LOW** — these are
   what the human is actually being asked to accept.
5. Give the **evidence**, each item linked to a ledger entry or pinned `repo@sha:path:line`.
6. For conflicts, present **each position with its own evidence**, side by side — do not
   pre-decide.
7. End with the **options** and the consequence of each (including "reject" and "ask for more").
8. Follow every rule in [reference/presentation-rules.md](reference/presentation-rules.md).

## Template
```markdown
## Decision requested: <one sentence>   — for: human:<role>
**Change Set:** CS-123 · **Tier:** HIGH (SENSITIVE_PATH: auth/) · **Snapshot:** SNAP-220

### Authority status
| Item | Status | Evidence |
|---|---|---|
| Unit + integration tests | VERIFIED (CI) | ENTRY-9981 |
| Code quality | REVIEWED: ACCEPT (code-reviewer, model family B) | ENTRY-9990 |
| Security | REVIEWED: REJECT (security-reviewer) | ENTRY-9993 |

### Needs your judgment
- QUESTION (blocking): ... [ENTRY-..]
- ASSUMPTION (impact MEDIUM, expires ...): ... [ENTRY-..]

### Options
1. Approve — consequence ...
2. Reject — consequence ...
3. Request changes / more evidence — ...
```

## Outputs
A markdown summary (PR comment, issue comment, or approval-request body) plus a ledger entry
referencing it.

## Enforcement
Guideline only — no enforcement point yet. The approval itself is enforced by the forge
(CODEOWNERS review / environment approval) per §5.10; this skill governs what the human sees.

## References
- [reference/presentation-rules.md](reference/presentation-rules.md)
- [../evidence-gate/SKILL.md](../evidence-gate/SKILL.md)
- [../../change-management/change-set/reference/approval-matrix.md](../../change-management/change-set/reference/approval-matrix.md)
