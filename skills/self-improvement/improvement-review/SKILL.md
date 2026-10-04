---
name: improvement-review
description: Cluster incidents, draft lessons with synthetic reproduction, route through human approval. Use on schedule or when a pattern fires.
metadata:
  group: self-improvement
  phase: 1
  binding: true
  plan-ref: "§4.2 (v3.1 revision, ADR 0006), §5.5"
  stage: LEARN
  inputs: [incident]
  outputs: [review-verdict]
  repo_roles: [planning]
---

# Improvement Review

## Purpose
Turn clusters of real failures into **lessons** — short, abstract, checkable, and shareable — and
into the smallest effective remedy, gated by a human. The platform never silently rewrites its
own skills; self-improvement gets no quieter path to production than a developer's code.

## When this applies
On a schedule (default: every 2 weeks during a pilot) or when a cluster crosses the threshold in
[reference/pattern-threshold.md](reference/pattern-threshold.md).

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). This skill runs at LEARN, on a schedule or on a pattern-threshold hit.

- **Inputs:** OPEN, `pattern_eligible` incidents in the project ledger.
- **BACKFILL:** if the project has no sanitization blocklist yet, build it with `scripts/build_blocklist.py` before drafting anything.
- **BLOCK:** a lesson that fails `lesson_lint.py` or `sanitize_check.py`, or whose reproduction is not red on the current skill, stays DRAFT — it can't reach REVIEWED.
- **Repo roles:** `planning` for the project ledger and blocklist inputs; skill revisions go to the platform repo by PR (skill files are control files — human-approved only).

## Procedure
1. **Collect.** `mcp:adlc.query_incidents` for `status: OPEN`, `pattern_eligible: true`. It
   returns signals and pointers, not content. `unverified-positive` never counts.
2. **Cluster** by `(skill, step, failure_class)`. Apply the threshold
   ([pattern-threshold.md](reference/pattern-threshold.md)); below it, leave incidents OPEN.
   Also list remedies whose `last_fired` is older than 6 months (step 9).
3. **Draft one lesson per cluster** in [lesson.schema.json](reference/lesson.schema.json) form.
   The drafter is a reviewer agent; it is never the role whose output failed. Write in skill
   terms only: `what_failed`, then `advice` with a condition and an observable
   ("When a story changes input handling, require ≥1 negative AC per validated field"), and a
   mechanical `check` if one exists. Use evidence pointers to understand the cluster, but never
   copy anything from them.
4. **Lint:** `python scripts/lesson_lint.py LESSON` must PASS. It checks that the skill and step
   exist in the catalog, the class is in the taxonomy, the advice is checkable (no "be careful",
   "make sure to consider"), and a GATE/LINT remedy has a `check`.
5. **Write a synthetic reproduction** per
   [eval-case-conversion.md](reference/eval-case-conversion.md): a minimal skill-creator
   `evals.json` case built from the lesson, never from the real case. Run it on the
   **current** skill: it must fail (red). If it passes, the reproduction does not capture the
   failure. Rewrite it, or dismiss the cluster.
6. **Select the remedy** per [remedy-and-lifecycle.md](reference/remedy-and-lifecycle.md):
   GATE or LINT when `check` is mechanical (enforcement, routed through the control-file
   process). SKILL_TEXT or EXAMPLE only for judgment failures. A SKILL_TEXT remedy must state
   where it goes and what it replaces or merges into, and the skill must stay within its size
   budget (body ≤ 500 lines).
7. **Draft the revision** as a PROPOSAL diff (never written to the skill path). Run
   skill-creator's loop: the reproduction must **pass on the revision (green)** and the skill's
   existing evals must not regress. The server then records the candidate as `REVIEWED` with
   the grading evidence.
8. **Sanitize:** `python scripts/sanitize_check.py lesson.json repro-evals.json --blocklist
   .adlc/blocklist.json --project-path <each project repo>` must PASS. It is fail-closed:
   anything that fails stays project-local.
9. **Prune:** for each remedy unfired for 6 months, propose removal (also a REVIEWED → APPROVED
   change). Removing dead rules matters as much as adding new ones.
10. **Human approval** per [human-approval-gate.md](reference/human-approval-gate.md): the human
    approves the lesson **and** its reproduction together. Only then does the revision merge,
    the reproduction become a permanent regression eval, and the lesson become shareable at
    `ORG` scope. Record the lesson with `mcp:adlc.record_lesson` and mark the incidents
    `CONVERTED` (new rows).

## Outputs
Lessons (`lesson.schema.json`), synthetic reproductions (`evals.json` cases), PROPOSAL diffs,
REVIEWED candidates with grading evidence, PRs awaiting human approval, pruning proposals.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.

| Rule | Enforced by |
|---|---|
| Lesson names a real skill/step and taxonomy class, with checkable advice | `scripts/lesson_lint.py` (BLOCK in Preflight) |
| Nothing unsanitized leaves the project | `scripts/sanitize_check.py`, fail-closed; `record_lesson` requires a PASS result |
| ORG scope only after human APPROVED | `lesson.schema.json` conditional; `record_lesson` rejects ORG without an APPROVED human event |
| Skill changes need human approval | Skill files are control files: managed-settings deny + control-file-guard; CRITICAL tier |
| Red on current, green on revision | Recorded in `repro`; `lesson_lint.py` rejects an APPROVED lesson without both true |
| Remedy choice and size budget | Guideline only — reviewed by the human approver |

## References
- [reference/pattern-threshold.md](reference/pattern-threshold.md)
- [reference/lesson.schema.json](reference/lesson.schema.json)
- [reference/eval-case-conversion.md](reference/eval-case-conversion.md)
- [reference/remedy-and-lifecycle.md](reference/remedy-and-lifecycle.md)
- [reference/human-approval-gate.md](reference/human-approval-gate.md)
- [../scripts/lesson_lint.py](../scripts/lesson_lint.py) · [../scripts/sanitize_check.py](../scripts/sanitize_check.py) · [../scripts/build_blocklist.py](../scripts/build_blocklist.py)
- [../failure-capture/reference/failure-taxonomy.md](../failure-capture/reference/failure-taxonomy.md)
- [ADR 0006](../../../docs/adr/0006-self-improvement-lessons.md)
