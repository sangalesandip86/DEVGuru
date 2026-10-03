# ADR 0006: Self-improvement records sanitized lessons, not use cases

- **Status:** Proposed. Requires human approval.
- **Date:** 2026-10-03
- **Revises:** plan §4.2 (`/self-improvement`)

## Context
v3's incident record stores the real task text (`prompt`), pinned project files (`repo@sha:path`), and Change Set and run IDs. Skills are shared across projects, so anything that flows into improvement work can leak customer names, code, data or domain detail into other projects.

The product owner asked that improvement records be short, abstract notes about what didn't work, written in skill terms, with no reference to the actual use case.

## Assessment of "abstract notes only"
Abstract notes are the right thing to *share*, but on their own they cannot drive improvement reliably:
- **They can't be run.** The §5.5 pipeline promotes a skill revision only after it passes evals (REVIEWED). A sentence cannot be executed as an eval.
- **They can't catch regressions.** Without a runnable case, a later edit can bring the failure back silently.
- **They invite vague fixes.** Notes like "be careful with validation" bloat skills without changing what the agent does.
- **They are unreliable when written at the moment of failure.** The agent that just failed is the least reliable diagnostician of that failure.
- **They can still leak.** An LLM asked to "abstract" a case can still copy identifying details into its note.

## Decision

### 1. Capture: deterministic first, per incident, local only
Each incident records:
- a **signal**: `skill`, `step`, `failure_class`, `signal_source`, `verification_strength`;
- **local evidence pointers**: ledger `entry_id`s only.

It carries **no free-text use-case content**.

- **Where `failure_class` comes from:** it is derived **deterministically** from the check that caught the failure, using `failure-class-map.json`. Examples:
  - DoR item `negative_ac_present` maps to `MISSING_NEGATIVE_CASE`.
  - An integrity-guard finding `assertion_removed` maps to `WEAKENED_TEST`.
  - A scope violation maps to `SCOPE_CREEP`.
  - A manifest diff with no linked DECISION maps to `UNDECLARED_DEVIATION`.
- **Judgment-only failures** are reviewer REJECTs or human overrides with no deterministic check behind them. These carry a short `note` of at most 280 characters, in skill terms. It is written by the **reviewer or human who caught the failure**, never by the agent that failed. It must pass the sanitization check.
- **The real case stays local.** Evidence lives in that project's Evidence Ledger, under its access controls and its retention period (default 90 days, configurable). Nothing from the case is copied into the incident.

### 2. Lessons: written per cluster, sanitized, shareable
`improvement-review` clusters incidents by `(skill, step, failure_class)` once the existing threshold is met (§4.2 `pattern-threshold.md`). For each cluster, a reviewer agent drafts one **lesson**:

```yaml
lesson_id: LES-14
skill: product-planning/story-writer
step: "Procedure 4 — write acceptance criteria"
failure_class: MISSING_NEGATIVE_CASE
occurrences: {incidents: 7, change_sets: 4, projects: 2}
what_failed: "AC for input-validation stories covered only valid input"
advice: "When a story changes input handling, require ≥1 negative AC per validated field"
check: "touches.input_validation → count(ac.kind == negative) ≥ 1"   # mechanical form, if one exists
remedy_kind: GATE | LINT | SKILL_TEXT | EXAMPLE                     # prefer GATE/LINT when `check` is mechanical
```

`lesson_lint.py` rejects any lesson that is missing:
- a skill and step that exist in the catalog;
- a taxonomy class;
- advice that can be checked (no vague verbs without a condition).

### 3. Synthetic reproduction: required before any change
For each lesson, the reviewer writes a **synthetic** minimal scenario, in skill-creator `evals.json` form, that triggers the failure class. It is built from the lesson and never copied from the real case. It is used like this:
- It must **fail on the current skill and pass on the revised skill** (red/green, the same rule ADR 0003 applies to tests).
- It then becomes a permanent regression eval.

### 4. Sanitization: deterministic gate plus human review
`sanitize_check.py` runs on every note, lesson and reproduction **before it leaves project scope**. It scans:
- for PII and secrets, reusing `fixture_pii_scan.py` and the secret-scanning rules;
- against a **per-project blocklist** built automatically from the project's glossary, repo names, service names, `adlc.workspace.yaml`, the people and team names in CODEOWNERS, and distinctive identifiers in `plans/`;
- for verbatim overlap with project files (shingle match).

The process is fail-closed: content that fails the scan stays local. A human reviewer at improvement-review approves the lesson and its reproduction together.

### 5. The remedy: checks over prose, and size-bounded skills
- **Choose the remedy by what can be checked.** If a lesson has a mechanical `check`, the remedy is a gate, lint or policy rule. Those are enforcement and go through the control-file process. Skill text is the fallback, for failures that need judgment.
- **Cap skill size.** Every SKILL.md has a size budget (default: body ≤ 500 lines, references loaded on demand). An accepted SKILL_TEXT remedy must state where it goes and what it replaces or merges into.
- **Prune rules that don't fire.** Each lesson records `last_fired`. A lesson remedy with no matching incidents for 6 months is put up for removal at improvement-review.

### 6. Sharing scope
| Scope | Default | Contents |
|---|---|---|
| Project | always | Incidents and local evidence |
| Organization | on, after sanitization + human approval | Lessons, synthetic reproductions, skill revisions |
| Cross-organization | **deferred** | Not built. It needs the signed skill supply chain that v3 already defers. |

## Consequences
- **Incident schema:** `prompt`, `files` and the free-text fields are removed. Signal fields, evidence pointers and an optional sanitized `note` are added.
- **New files:**
  - `failure-class-map.json` and `failure-taxonomy.md` (about 15 classes);
  - `lesson.schema.json`;
  - `lesson_lint.py`, `sanitize_check.py`, `build_blocklist.py`.
- **evidence_ledger module:**
  - `record_incident` rejects free-text use-case fields;
  - new `record_lesson` (sanitization result required, scope `ORG` only after a human APPROVED);
  - `query_incidents` returns pointers, not content.
- **Grounding:** the agent that failed is never the author of its own lesson.
