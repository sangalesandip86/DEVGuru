---
name: test-case-design
description: Derive code-blind test designs from ACs using boundary-value, equivalence, and decision-table techniques. Use when a story becomes READY.
metadata:
  group: testing
  phase: 1
  binding: true
  plan-ref: "§4.13, §4.12 refinement, §4.7 qa-derive"
  stage: DESIGN
  inputs: [ready-story, contract]
  outputs: [test-design]
  repo_roles: [planning, contracts]
---

# Test Case Design (the oracle)

## Purpose
Decide **what correct behaviour is** before anyone looks at the code. Expected outcomes come from
the acceptance criteria and contracts, never from the implementation. A test whose expectations
are read from the code turns its bugs into green tests (ADR 0003). This skill is run by
`qa-derive`, which is technically denied access to implementation paths.

## When this applies
- **During refinement.** You produce a test *outline* from the AC alone. That outline is the DoR JUDGMENT
  "AC are testable" (§4.12), recorded as REVIEWED against the current `ac_hash`.
- **When the story becomes READY.** You expand the outline into the frozen design,
  `plans/test-designs/ST-n.yaml` (or `.feature` files in BDD repos, see
  [bdd-feature-authoring](../bdd-feature-authoring/SKILL.md)).
- **When the AC changed after READY** (the AC freeze). The previous design is invalidated, and you redo it.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve the `planning` repo role (where `plans/` lives) and the `contracts` role, if the story
   has `touches.api_contracts`. A missing planning repo means BACKFILL via workspace-resolver.
2. **Story input.**
   - READY story with the current `ac_hash`: SATISFIED.
   - Story in REFINING: produce an **outline only**. It is the DoR testability evidence, not a frozen design.
   - No story, or AC in a tracker or doc: **ADOPT** via requirement-intake/story-writer (imported as
     DRAFT), or **BACKFILL** PLAN (refinement only).
   - Never design against an AC you cannot cite as `repo@sha:path`.
3. **Contracts.** For API/event stories, the OpenAPI, Pact or schema must resolve. If it is missing, raise
   a QUESTION addressed to the architect (or `human:tech-lead` in Degraded Mode). Don't infer the
   contract from code.
4. **Allowed reads.** Story, requirement, contracts, `.adlc/catalog/step-patterns.json`. Nothing under
   implementation paths. Attempts are denied by permissions anyway (§5.6).

## Procedure
1. **List what the AC says.** For each `ST-n/AC-n`: the inputs, the rules, the observable outcomes, and the
   `kind` (functional, negative or nfr). Anything the AC doesn't state is a gap, never an assumption you
   fill in silently.
2. **Pick techniques per AC.** See [reference/techniques.md](reference/techniques.md).
   - Inputs with ranges or lengths: boundary-value analysis (BVA) plus equivalence partitions.
   - Combinations of conditions leading to outcomes: a decision table.
   - Lifecycle or status flows: state transitions (valid *and* invalid transitions).
   - Several independent parameters: pairwise (PICT), and say which pairs are covered.
   - Known failure modes (timeouts, duplicates, concurrency, injection, empty states): error guessing,
     each citing *why*.
3. **Define partitions, not values.** For each input, state the partitions and limits *as specified*, for example
   `amount: [0.01 .. 10000], precision 2`. The values come from
   [boundary_values.py](../../test-data/test-data-synthesis/scripts/boundary_values.py) at implementation time.
4. **Write scenarios.** Each scenario has:
   - an ID `ST-n/SC-n`;
   - `ac_refs`;
   - the technique;
   - Given/When/Then;
   - an **expected outcome stated observably** (status code, message key, state, event emitted);
   - data partitions;
   - a tier hint (unit, component, contract, BDD or E2E, the lowest level that proves it, see
     [test-pyramid-advisor](../../test-architecture/test-pyramid-advisor/SKILL.md)).
5. **Cover every AC.** Each `automated` AC needs at least one scenario, and every story except DOCUMENTATION
   and SPIKE needs at least one `negative` scenario. NFR AC get a measurable threshold scenario.
6. **Gaps.** Raise them as **one batched QUESTION per story** to `human:product-owner`, and never ask
   empty-handed: include your proposed expected outcome as option A.
   - If the story is HIGH or CRITICAL, block the freeze until the questions are answered.
   - If the story is LOW, proceed on an expiring ASSUMPTION per the
     [ask-vs-assume matrix](../../../grounding/ambiguity-escalation/reference/ask-vs-assume-matrix.md).
7. **Reuse step phrasing** from `step-patterns.json` when the repo uses BDD
   ([bdd-feature-authoring](../bdd-feature-authoring/SKILL.md)).
8. **Freeze.** Write `plans/test-designs/ST-n.yaml` with `ac_hash` set to the story's current hash, and open a PR
   (`REPO_WRITE`). Record a REVIEWED entry (testability ACCEPT) carrying that `ac_hash`.

## Spec-versus-code discrepancies
Later, test-engineer may find implementation limits that differ from your partitions, for example a
validator capping at 50 where the AC says 100. That is a **QUESTION or a defect**. It never edits the
design. Code-derived information may *add* scenarios, such as an undocumented enum value. Those are
proposed back to you and appended under a new SC ID with `source: implementation-finding`, and
they need your REVIEWED before they count.

## Outputs
- `plans/test-designs/ST-n.yaml`, as a PROPOSAL until merged. Schema:
  [reference/test-design.schema.json](reference/test-design.schema.json), documented in
  [reference/test-design-schema.md](reference/test-design-schema.md).
- REVIEWED: test-design ACCEPT (testability) pinned to `ac_hash`. Never VERIFIED. A test passing is VERIFIED
  only by CI (§5.5).
- QUESTION and ASSUMPTION entries for gaps.

## Enforcement
**Enforced** — see rules below.

- Code-blindness: qa-derive's implementation-path denial (§5.6 row "QA Pass 1 is implementation-blind").
- Oracle protection: test-engineer is write-denied on `plans/test-designs/**` and `**/*.feature`
  (§5.6 row "Test expectations come from AC, not code").
- AC freeze: `plan_lint.py` AC-hash check plus `test_integrity_guard.py` (an expectation change requires an AC-hash change).
- Coverage of AC: `ac_coverage.py` at DONE (§4.12).

## References
- [reference/techniques.md](reference/techniques.md), [reference/test-design-schema.md](reference/test-design-schema.md), [reference/test-design.schema.json](reference/test-design.schema.json)
- [acceptance-criteria-standard](../../../product-planning/story-writer/reference/acceptance-criteria-standard.md)
- [story-refinement](../../../product-planning/story-refinement/SKILL.md), [qa-derive role](../../../roles/qa-derive/ROLE.md)
- [evidence-gate](../../../grounding/evidence-gate/SKILL.md), [ambiguity-escalation](../../../grounding/ambiguity-escalation/SKILL.md)
