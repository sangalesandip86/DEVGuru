---
name: ambiguity-escalation
description: Decides whether to ask a QUESTION or record an ASSUMPTION when information is missing, and applies fail-safe defaults (toward more scrutiny) when evidence is incomplete. Use whenever a requirement, dependency, compatibility result, or risk tier is unclear.
metadata:
  group: grounding
  phase: 0
  binding: true
  plan-ref: "§4.1, §5.2, §5.3"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

<!-- reconstructed: v2 source not provided; review -->

# Ambiguity Escalation

## Purpose
When evidence is incomplete, resolve toward **more scrutiny, not less**. Decide explicitly
whether a gap warrants asking a human (QUESTION) or proceeding on a recorded, expiring
ASSUMPTION — never a silent guess.

## When this applies
- A requirement or acceptance criterion is vague, contradictory, or missing
- A dependency, compatibility result, or risk tier cannot be determined
- `grounding/evidence-gate` finds an unsourced claim
- Two roles disagree on a fact or a risk level

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the open ambiguity plus whatever partial evidence exists; the ask-vs-assume matrix needs the effective risk tier, so resolve the tier first (fail-safe HIGH if it can't be computed).
- **ASK** is this skill's own outcome: one batched QUESTION per story or Change Set, with a proposed default and explicit options.
- **ADOPT:** open questions found in ingested docs or tracker items are imported as OPEN QUESTIONs citing their source, not silently resolved.
- **Repo roles:** none required; QUESTIONs are written to the Evidence Ledger.

## Procedure
1. Name the gap precisely: what is unknown, and what would resolve it.
2. Check whether a **fail-safe default** covers it
   ([reference/fail-safe-defaults.md](reference/fail-safe-defaults.md)). If yes, apply the
   default and record it as an ASSUMPTION citing the default rule — never the convenient reading.
3. Otherwise classify using the
   [ask-vs-assume matrix](reference/ask-vs-assume-matrix.md) on two axes: **cost of being wrong**
   and **reversibility**.
4. ASK → write a QUESTION entry: `state: OPEN`, `blocking: true|false`, addressed to a role or
   `human:*` approver, with the options you see and the evidence for each. **Never ask
   empty-handed** (platform-wide rule, ADR 0003):
   - Every QUESTION carries a **proposed default or draft** — the answer you would use if
     told "go ahead". For data questions, attach a short schema-valid draft payload (3–5 lines).
   - Every QUESTION carries **explicit options**, including accepting the draft. For data, these
     are: approve synthesis / supply data / answer that it is out of scope.
   - **Batch questions per story or Change Set** into one QUESTION entry addressed to the right
     human role (`human:product-owner`, the domain owner, `human:tech-lead`, ...). Don't block
     field by field or ask inline one question at a time.
   - The [ask-vs-assume matrix](reference/ask-vs-assume-matrix.md) decides by tier whether the
     batch blocks or whether work proceeds on an expiring ASSUMPTION that equals the draft.
5. ASSUME → write an ASSUMPTION entry with `impact` (LOW/MEDIUM/HIGH), `expires_at`, and the
   observation that would invalidate it.
6. A `blocking: true` QUESTION that is OPEN fails the Change Set's completion criteria
   (`change-management/change-set/reference/completion-criteria.md`). An unexpired ASSUMPTION
   with impact > LOW does too.
7. If uncertainty matches a named reason code (`UNRESOLVED_DEPENDENCY`, `UNKNOWN_BLAST_RADIUS`,
   `SENSITIVE_PATH`, `COMPATIBILITY_UNKNOWN`), request a one-level risk escalation — exactly one,
   never more (`change-management/risk-tiering/reference/escalation-reason-codes.md`).
8. If the required capability for the tier is not built yet, route to the named human standing
   in for that role (Degraded Mode, §2) — never block indefinitely, never skip.

## Outputs
QUESTION entries (OPEN/ANSWERED/EXPIRED, `blocking`), ASSUMPTION entries (`impact`,
`expires_at`), and escalation requests carrying a reason code.

## Enforcement
- Completion-criteria gate on blocking QUESTIONs and impact > LOW ASSUMPTIONs: enforced by the
  Change Management server (Phase 2) or by the PR required-check in forge-native mode.
- Choosing ASK vs ASSUME correctly: **guideline only** — audited by human review and
  self-improvement (incorrect assumptions surface as CHALLENGED corrections).

## References
- [reference/ask-vs-assume-matrix.md](reference/ask-vs-assume-matrix.md)
- [reference/fail-safe-defaults.md](reference/fail-safe-defaults.md)
- [../evidence-gate/SKILL.md](../evidence-gate/SKILL.md)
- [../../core/fact-classification/SKILL.md](../../core/fact-classification/SKILL.md)
