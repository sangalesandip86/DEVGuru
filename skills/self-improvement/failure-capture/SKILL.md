---
name: failure-capture
description: Records each negative, positive, efficiency, or production signal as a project-local incident containing only a signal (skill, step, failure_class derived deterministically from the catching check) and ledger pointers — never task text, files, or use-case content. Use whenever a check, reviewer, human, or production event catches a skill failure or a strongly verified success.
metadata:
  group: self-improvement
  phase: 1
  binding: true
  plan-ref: "§4.2 (v3.1 revision, ADR 0006)"
  stage: LEARN
  inputs: [change-set]
  outputs: [incident]
  repo_roles: []
---

# Failure Capture

## Purpose
Turn what actually happens in real use into **signals** that `improvement-review` can cluster,
without copying the real case anywhere. Skills are shared across projects, so an incident holds
no customer names, code, data, or domain detail. The case itself stays in the project's own
Evidence Ledger, under its access controls and retention period (default 90 days, configurable).

## When this applies
On any trigger in [reference/trigger-signals.md](reference/trigger-signals.md): a deterministic
check fails (DoR/DoD item, test-integrity finding, control-file guard, dependency-decision check,
scope check, evidence gate, ...), a reviewer REJECTs, a human overrides, a run is strongly
verified clean (positive), a budget overruns (efficiency), or a production event is linked to a
Change Set.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. This skill runs at LEARN, and also passively during any stage when a trigger signal fires.

- **Inputs:** the trigger (check ID or reviewer/human verdict) and the ledger entries it refers to.
- **SATISFIED** when the evidence entries can be queried in the project ledger.
- **ASK:** never. If the failing skill or step can't be determined from the evidence, the incident is not written; record a RISK entry instead.
- **Repo roles:** none required; incidents are ledger records.

## Procedure
1. **Identify the catching check.** If a deterministic check caught the failure, take its
   `check_id` (`<checker>:<finding>`, e.g. `dor:negative_ac`,
   `test-integrity:ASSERTION_REMOVED`) and look up `failure_class` in
   [reference/failure-class-map.json](reference/failure-class-map.json). Do not choose the class
   yourself. A map entry with `class: null` is process state — write no incident.
2. **Judgment-only failures** (a reviewer REJECT or human override with no check behind it):
   `check_id: null`. The **reviewer or human who caught it** picks the class from
   [reference/failure-taxonomy.md](reference/failure-taxonomy.md) and writes a `note`:
   ≤280 characters, in skill terms, with no project names, data, or code. The failing agent
   never writes the note (`note_author_role` ≠ `agent_role`). The note must pass
   `scripts/sanitize_check.py` before the incident is recorded.
3. **Name the skill and step:** the catalog path of the skill whose output failed
   (`product-planning/story-writer`), and the heading or numbered step of its SKILL.md that
   produced the output (`Procedure 4 — write acceptance criteria`).
4. **Point at the evidence:** `evidence_refs` holds ledger `entry_id`s only. Never paste task
   text, prompts, file paths, diffs, or values into the incident.
5. **Positive-signal quality gate:** a positive signal is `pattern_eligible` only when
   verification was strong — `ac-coverage` VERIFIED (acceptance criteria actually exercised) and
   changed-code coverage recorded. Otherwise use `signal_type: unverified-positive`,
   `pattern_eligible: false`.
6. Record with `mcp:adlc.record_incident`. The evidence_ledger module rejects free-text use-case
   fields, derives `agent_role` from the evidence entries, and returns pointers, not content, from
   `query_incidents`.
7. **Production events** follow [reference/production-feedback.md](reference/production-feedback.md):
   a local correcting INFERENCE in the ledger plus an incident holding pointers and a class.
8. Never modify a skill, prompt, or policy here. That is `improvement-review`, through the
   lesson → reproduction → REVIEWED → APPROVED pipeline.

## Outputs
- Incident records (signal + pointers), schema
  [reference/incident.schema.json](reference/incident.schema.json)
- For production events: a CHALLENGED correcting ledger entry (local INFERENCE)

## Enforcement
| Rule | Enforced by |
|---|---|
| No use-case content in incidents | `incident.schema.json` (`additionalProperties: false`); `record_incident` rejects free-text fields |
| Class derived from the check, not chosen | `failure-class-map.json`; drift test `tests/test_failure_class_map.py` fails CI when a new DoR/DoD item or integrity code is unmapped |
| Failing agent never authors the note | `x-not-equal` on `note_author_role` / `agent_role`, checked by `record_incident` |
| Note is sanitized | `note_sanitize.result: PASS` required by the schema; produced by `sanitize_check.py` |
| Append-only correction | Ledger tool surface (no update/delete) |
| Choosing the right skill/step for a judgment-only failure | Guideline only — audited at improvement-review by `lesson_lint.py` |

## References
- [reference/trigger-signals.md](reference/trigger-signals.md)
- [reference/incident-schema.md](reference/incident-schema.md) · [reference/incident.schema.json](reference/incident.schema.json)
- [reference/failure-taxonomy.md](reference/failure-taxonomy.md) · [reference/failure-class-map.json](reference/failure-class-map.json)
- [reference/production-feedback.md](reference/production-feedback.md)
- [../scripts/sanitize_check.py](../scripts/sanitize_check.py)
- [../improvement-review/SKILL.md](../improvement-review/SKILL.md)
- [ADR 0006](../../../docs/adr/0006-self-improvement-lessons.md)
