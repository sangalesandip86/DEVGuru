---
name: evidence-gate
description: Ensures every claim in a structured artifact (handoff, DECISION, RISK, QUESTION, approval summary) cites a source; converts unsourced claims into QUESTIONs or tagged, expiring ASSUMPTIONs. Use whenever producing or accepting any structured artifact.
metadata:
  group: grounding
  phase: 0
  binding: true
  plan-ref: "§4.1, §1"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Evidence Gate

## Purpose
No claim in a structured artifact leaves any skill without a cited source. An unsourced
claim never passes through as a silent FACT — it becomes a QUESTION or a tagged, expiring
ASSUMPTION.

## When this applies
Always. This skill is binding for every role and every risk tier. It applies to these
**structured artifacts**:

- Handoffs between roles (`roles/reference/handoff-schema.md`)
- DECISION, RISK and QUESTION ledger entries
- Approval summaries presented to a human (`grounding/human-review-format`)

It does **not** apply sentence-by-sentence to free-form reasoning. See
[reference/evidence-gate-scope.md](reference/evidence-gate-scope.md) for exactly what it does
and does not guarantee — do not oversell it.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the structured artifact being produced or accepted (handoff, DECISION, RISK, QUESTION, approval summary) and the sources it cites.
- **ADOPT:** artifacts imported by brownfield adoption keep their original citations, re-anchored as `repo@sha:path` or `doc@hash#section`; a claim with no recoverable source is converted to a QUESTION, never carried over as FACT.
- **ASK:** only through ambiguity-escalation, never empty-handed.
- **Repo roles:** whichever repos the cited sources live in; resolve each cited `repo@sha` through the workspace resolver so citations stay pinned.

## Procedure
1. Before emitting a structured artifact, enumerate every claim it contains.
2. For each claim, attach one accepted source:
   - `file:line` — pinned as `repo@sha:path:line` when crossing a handoff
   - command output — reference the hook-written FACT entry id (`ENTRY-…`), never paste-and-assert
   - doc URL — with retrieval date; trust level `EXTERNAL_STRUCTURED` or `EXTERNAL_UNSTRUCTURED`
   - user statement — quote it and reference the ledger entry that recorded it
3. If a claim has no source:
   - If it **blocks** progress or a wrong guess is costly → convert to a `QUESTION`
     (`state: OPEN`, `blocking: true|false`) and follow `grounding/ambiguity-escalation`.
   - Otherwise → record an `ASSUMPTION` with `impact` (LOW/MEDIUM/HIGH), an `expires_at`
     (default: end of the Change Set's current state), and the reason it was assumed.
4. A derived claim is an `INFERENCE` and must list `input_references` (the evidence entry ids
   it was derived from). An inference with no inputs is an ASSUMPTION.
5. Never label your own claim `FACT`. FACT entries are written by hooks from command output
   and file reads (`core/fact-classification`).
6. Reject an inbound handoff whose claims lack sources: return it to the sender with the list
   of unsourced claims (counts as a structurally-invalid output — RETRY policy, see
   `grounding/agent-failure-modes`).

## Outputs
- QUESTION entries (with `blocking` flag and OPEN state) for unsourced blocking claims
- ASSUMPTION entries (with `impact`, `expires_at`) for unsourced non-blocking claims
- INFERENCE entries with `input_references`
- A pass/fail note on the handoff: `evidence_gate: PASS | FAIL(<claim ids>)`

## Enforcement
- FACT grounding is enforced: hooks write FACT entries directly; the model never self-reports a
  FACT (§5.6 row "FACT entries are grounded").
- The ledger server rejects INFERENCE entries without `input_references` and FACT entries
  without `source` (schema validation in `core/schemas/ledger-entry.schema.json`).
- Sourcing of every claim inside a handoff body: **guideline only** beyond the schema check —
  caught downstream by QA, code review, and human review.

## References
- [reference/evidence-gate-scope.md](reference/evidence-gate-scope.md)
- [../../core/fact-classification/SKILL.md](../../core/fact-classification/SKILL.md)
- [../ambiguity-escalation/SKILL.md](../ambiguity-escalation/SKILL.md)
- [../../core/evidence-ledger/SKILL.md](../../core/evidence-ledger/SKILL.md)
