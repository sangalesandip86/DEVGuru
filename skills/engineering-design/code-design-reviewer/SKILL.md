---
name: code-design-reviewer
description: Reviews a code change for design quality — SOLID adherence, known anti-patterns, and performance hazards — and emits a REVIEWED ACCEPT/REJECT with file:line evidence. Use when a Change Set's gates include code review at MEDIUM tier or above, or when asked to assess the design of a diff, module, or class.
metadata:
  group: engineering-design
  phase: progressive
  binding: false
  plan-ref: "§4.9"
  stage: REVIEW
  inputs: [change-set]
  outputs: [review-verdict]
  repo_roles: [app]
---

# Code Design Reviewer

<!-- reconstructed: v2 source not provided; review -->

## Purpose

Give the `code-reviewer` role (and any human reviewer) a consistent, evidence-backed lens for
design quality: responsibility boundaries, coupling, extensibility, and performance hazards
that tests will not catch. The output is a judgment, so it is `REVIEWED` — never `VERIFIED`.

## When this applies

- Routed in by `skill-routing` for MEDIUM+ tier changes that touch application code.
- On request: "review the design of…", "is this refactor sound?", "why is this class so hard to change?".
- Not for: formatting/lint (deterministic tools own that), requirement coverage (`qa-derive`),
  security findings (`security-reviewer`).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Runs at REVIEW on a Change Set at VERIFYING.

- **Inputs:** the Change Set diff pinned to its snapshot, plus the story and design notes.
- **BLOCK:** a Change Set not yet at VERIFYING isn't reviewed — report that it's early.
- **Repo roles:** `app`.

## Existing project standards
On an existing repo, load [project-conventions](../project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Review conformance against `conventions.json` and the golden files near the change; generic design advice from this skill never overrides a declared project standard.

## Procedure

1. **Establish scope.** Read the Change Set diff and its pinned snapshot. Review only files in
   scope; note out-of-scope smells as a separate, non-blocking observation.
2. **Establish context numbers.** Look for stated load, data volume, and latency targets in the
   requirement, ADRs, or the Change Set. If a performance finding depends on a number that is not
   stated (e.g., "is O(n²) acceptable here?" with unknown n), raise a `QUESTION` — do not guess.
3. **Walk the three checklists** in order, recording each finding with `file:line`:
   - [`reference/solid-principles.md`](reference/solid-principles.md)
   - [`reference/anti-patterns.md`](reference/anti-patterns.md)
   - [`reference/performance-checklist.md`](reference/performance-checklist.md)
4. **Grade each finding** by severity:
   - `BLOCKER` — correctness or maintainability defect that will cause bugs or block the next
     known change (cite the requirement or roadmap item).
   - `MAJOR` — a concrete design cost that should be fixed in this Change Set.
   - `MINOR` — improvement; never blocks.
5. **Separate evidence from opinion.** A finding citing code (`file:line`) and a consequence is a
   `RISK`. A preference without a demonstrable consequence is at most `MINOR` and labelled as such.
6. **Decide.** `REJECT` if any `BLOCKER`, or if `MAJOR` findings are unaddressed after the one
   revision cycle allowed by `../../roles/reference/conflict-resolution.md`. Otherwise `ACCEPT`.
7. **Do not compare against deterministic gates.** If lint, type-check, or complexity tools ran in
   CI, cite their result as a FACT from the ledger; do not re-derive it by reading code.

## Outputs

- One `DECISION` entry: `REVIEWED` with `ACCEPT` or `REJECT`, referencing every `RISK` entry it relies on.
- `RISK` entries per BLOCKER/MAJOR finding: `{file:line, principle/pattern, consequence, suggested fix}`.
- `QUESTION` entries for missing context numbers (blocking only if a BLOCKER depends on the answer).
- Handoff to `developer` per `../../roles/reference/handoff-schema.md`.

## Enforcement

- Every claim must carry a source per `../../grounding/evidence-gate/SKILL.md`.
- That this skill can only produce `REVIEWED` is enforced by the MCP tool surface (§5.6 row 1):
  no agent-callable tool sets `VERIFIED` or `APPROVED`.
- The severity rubric and checklist coverage are **guideline only — no enforcement point yet**.
- For HIGH/CRITICAL tiers, run on a different model family from the implementing agent
  (`../../roles/reference/reviewer-diversity.md`).

## References

- [`reference/solid-principles.md`](reference/solid-principles.md)
- [`reference/anti-patterns.md`](reference/anti-patterns.md)
- [`reference/performance-checklist.md`](reference/performance-checklist.md)
- `../../grounding/evidence-gate/SKILL.md`
- `../../roles/code-reviewer/ROLE.md`
- `../scale-readiness-reviewer/SKILL.md` — for system-level (not code-level) performance questions
