---
name: story-refinement
description: Runs the three-amigos refinement loop (product-planner drafts, qa-derive tests the AC blind, developer checks feasibility and size) that turns a drafted story into one that can pass the Definition of Ready; splits oversized stories. Use after story-writer, whenever a story is NOT_READY, or when AC change after READY.
metadata:
  group: product-planning
  phase: 1
  binding: false
  plan-ref: "§4.12, §4.7"
  stage: PLAN
  inputs: [ready-story]
  outputs: [ready-story]
  repo_roles: [planning, app]
---

# Story Refinement

## Purpose
Writing a story and making it implementation-ready are different activities, done by different
roles. Refinement is the loop that produces the **JUDGMENT evidence** the DoR needs:
- qa-derive's testability review;
- developer's feasibility and size review;
- architect or security-reviewer reviews where the story type requires them.

It also splits stories that are too large.

## When this applies
- A story was drafted or changed and has not passed the readiness gate.
- `readiness_gate.py` reports NOT_READY. Its missing items are the agenda.
- `plan_lint.py` reports `REQUIRES_REFINING` (the AC changed after READY).
- A story is sized `L`.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Stage PLAN.

- **Inputs:** DRAFT or REFINING stories.
- **ADOPT:** imported stories enter refinement directly; they're never treated as READY until the gate says so.
- **Repo roles:** `planning`, `app` (developer feasibility check reads it).

## Procedure
Follow [reference/refinement-protocol.md](reference/refinement-protocol.md). In short:

1. **Run the gate first** (as a dry run, or read the last CI result) and start from its MISSING items, not from a blank checklist.
2. **product-planner** fixes the structural gaps: missing fields, AC standard, tags, `touches`, `affected_paths`. Gaps it can't close from sources become QUESTIONs ([ambiguity-escalation](../../grounding/ambiguity-escalation/SKILL.md)).
3. **qa-derive** reads the story only. Its tool permissions deny implementation paths. It returns either a test outline, one or more test ideas per criterion including the negative paths, or QUESTIONs about criteria it cannot test.
   - On success it records `REVIEWED` / `ACCEPT` for item `qa_testability`, pinned to the current AC hash.
   - The outline is saved as qa-derive's frozen Pass 1 input.
4. **developer** checks feasibility and size against the current snapshot: the modules in `affected_paths`, the dependencies, and the predicted diff size.
   - It records `REVIEWED` / `ACCEPT` or `REJECT` for item `developer_feasibility`, pinned to the AC hash, with evidence.
   - It proposes a split when the predicted size is `L`.
5. **Type-required reviewers** act as listed in [`policies/dor-policy.yaml`](../policies/dor-policy.yaml): architect for contracts, security-reviewer for SECURITY or RESTRICTED stories.
6. **Split if needed** using [epic-decomposer/reference/slicing-patterns.md](../epic-decomposer/reference/slicing-patterns.md):
   - The original story is marked SPLIT by the projection job once its children merge.
   - The children carry `follow_up_of`. The original's AC ids are never reused.
7. **Stop conditions:**
   - The gate reports READY;
   - or 3 back-and-forth cycles between any two roles end without agreement, which escalates to a human per [conflict-resolution](../../roles/reference/conflict-resolution.md);
   - or a REJECT, which blocks within that reviewer's domain until a human lifts it.

## Outputs
- An updated story file (PR) and possibly split children.
- Ledger entries: REVIEWED records for `qa_testability`, `developer_feasibility` and others; QUESTIONs; size PROPOSALs.
- qa-derive's test outline, which becomes its Pass 1 input, pinned to `repo@sha:path` with the AC hash.

## Enforcement
- **Reviews count only from the right actor at the current AC hash:** `readiness_gate.py`. SYSTEM or VERIFIED records never satisfy a judgment.
- **qa-derive is code-blind:** tool-permission denial of implementation paths (plan §5.6 row "QA Pass 1 is implementation-blind"), generated in `dist/claude/settings.roles.json` from [`roles/qa-derive/role.yaml`](../../roles/qa-derive/role.yaml).
- **Max 3 cycles:** orchestrator counter (plan §4.1, §4.7). It is a guideline until the orchestrator enforces it.

## References
- [reference/refinement-protocol.md](reference/refinement-protocol.md) · [reference/sizing-guide.md](reference/sizing-guide.md)
- [definition-of-ready](../definition-of-ready/SKILL.md) · [story-writer](../story-writer/SKILL.md)
- [roles/reference/conflict-resolution.md](../../roles/reference/conflict-resolution.md) · [roles/reference/handoff-schema.md](../../roles/reference/handoff-schema.md)
