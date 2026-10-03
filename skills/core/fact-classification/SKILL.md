---
name: fact-classification
description: Classifies every statement as FACT, INFERENCE, ASSUMPTION, PROPOSAL, QUESTION, DECISION, or RISK, and tracks lifecycle state for DECISION/PROPOSAL entries. Use whenever recording to the evidence ledger or labelling claims in any structured artifact.
metadata:
  group: core
  phase: 0
  binding: true
  plan-ref: "§4.3, §5.1"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

<!-- reconstructed: v2 source not provided; review -->

# Fact Classification

## Purpose
A shared, strict vocabulary for what kind of statement something is, so that a guess is never
mistaken for an observation and an agent's opinion is never mistaken for a verification.

## When this applies
Every ledger write and every claim inside a structured artifact (handoff, approval summary).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** each claim about to be recorded, with its source.
- **ADOPT:** claims imported from existing docs or tickets are never classified FACT by the model — FACTs come only from hooks; imported claims start as ASSUMPTION or QUESTION until verified.
- **Repo roles:** none required.

## Procedure
1. Classify the statement using the decision order in
   [reference/taxonomy.md](reference/taxonomy.md): first ask "did a system observe this?"
   (FACT — but only hooks write those), then "is it derived from cited evidence?" (INFERENCE),
   and so on.
2. If you are about to write FACT: stop. Cite the hook-written FACT entry instead. If none
   exists, run the command or read the file so the hook records it, then cite that.
3. If you cannot cite inputs for a derived claim, it is an ASSUMPTION, not an INFERENCE.
4. For DECISION and PROPOSAL, set `lifecycle_state` (`DRAFT` or `PROPOSED`; `REVIEWED` if you
   are a reviewing role with evidence attached). Never `VERIFIED` or `APPROVED`.
5. When in doubt between two classes, pick the weaker one (ASSUMPTION over INFERENCE,
   QUESTION over ASSUMPTION for anything blocking).

## Outputs
Correctly classified ledger entries and handoff claims.

## Enforcement
- FACT entries are grounded: hooks write FACT entries directly; the model never self-reports a
  FACT (§5.6). The ledger server rejects FACT from AGENT callers.
- INFERENCE without `input_references` is rejected by schema validation.
- Choosing between INFERENCE / ASSUMPTION / QUESTION correctly: guideline only — audited by
  review and self-improvement.

## References
- [reference/taxonomy.md](reference/taxonomy.md)
- [../evidence-ledger/SKILL.md](../evidence-ledger/SKILL.md)
- [../../grounding/evidence-gate/SKILL.md](../../grounding/evidence-gate/SKILL.md)
- [../../grounding/ambiguity-escalation/SKILL.md](../../grounding/ambiguity-escalation/SKILL.md)
