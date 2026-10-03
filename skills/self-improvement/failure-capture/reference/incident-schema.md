# Incident Schema

Machine-readable form: [`incident.schema.json`](incident.schema.json) (`additionalProperties: false`).
Incidents are another table in the project's Evidence Ledger, not a separate logging system.

Per [ADR 0006](../../../../docs/adr/0006-self-improvement-lessons.md), an incident is a
**signal plus local pointers**. v3's `prompt`, `files`, `expected_output`, FACT/INFERENCE text,
`change_set_id`, and `run_id` are removed: anything that flows into improvement work may cross
project boundaries, so nothing from the real case goes in. The evidence stays behind the
`evidence_refs` pointers, in the project ledger, under its access controls and retention.

## Fields

| Field | Required | Description |
|---|---|---|
| `incident_id` | yes | `INC-…`, server-assigned |
| `parent_incident_id` | no | Status changes are new rows referencing the original (append-only) |
| `signal_type` | yes | `negative` / `positive` / `unverified-positive` / `efficiency` / `production` |
| `signal_source` | yes | `AGENT` / `REVIEWER` / `HUMAN` / `PRODUCTION` |
| `skill` | yes | Catalog path of the skill whose output failed, e.g. `product-planning/story-writer` |
| `step` | yes | Heading or numbered step of that SKILL.md, e.g. `Procedure 4 — write acceptance criteria` |
| `failure_class` | yes | One of the [taxonomy](failure-taxonomy.md) classes; `null` for positive/efficiency |
| `check_id` | for negative/production | `<checker>:<finding>` key into [failure-class-map.json](failure-class-map.json); `null` = judgment-only |
| `agent_role` | yes | Role whose output failed (server-derived from the evidence entries) |
| `tool` | no | `claude-code` / `copilot` |
| `verification_strength` | yes | `{changed_code_coverage, acceptance_criteria_exercised}` |
| `pattern_eligible` | yes | `false` for `unverified-positive` |
| `evidence_refs` | yes | Ledger `entry_id`s only (`ENTRY-…`), ≥1 |
| `note` | judgment-only | ≤280 chars, skill terms, sanitized |
| `note_author_role` | with `note` | Reviewer role or `human:<role>`; **must differ from `agent_role`** |
| `note_sanitize` | with `note` | `{result: PASS, checked_at}` from `sanitize_check.py` |
| `platform_release_sha` | yes | Skill/policy version in effect |
| `recorded_at` | yes | Server timestamp |
| `status` | yes | `OPEN` / `CLUSTERED` / `CONVERTED` / `DISMISSED` |

## Examples

Deterministic catch:
```json
{
  "incident_id": "INC-7f3a91c2d0e4", "signal_type": "negative", "signal_source": "AGENT",
  "skill": "product-planning/story-writer", "step": "Procedure 4 — write acceptance criteria",
  "check_id": "dor:negative_ac", "failure_class": "MISSING_NEGATIVE_CASE", "agent_role": "product-planner",
  "verification_strength": {"changed_code_coverage": null, "acceptance_criteria_exercised": false},
  "pattern_eligible": true, "evidence_refs": ["ENTRY-3f9c2ab01d4e"],
  "platform_release_sha": "a1b2c3d", "recorded_at": "2026-10-03T10:00:00Z", "status": "OPEN"
}
```

Judgment-only catch (code-reviewer REJECT):
```json
{
  "...": "...",
  "check_id": null, "failure_class": "DESIGN_DEFECT", "agent_role": "developer",
  "note": "Validation duplicated in handler and service layer; skill step gave no guidance on where validation lives",
  "note_author_role": "code-reviewer",
  "note_sanitize": {"result": "PASS", "checked_at": "2026-10-03T10:02:00Z"}
}
```

## Why no free text
- Abstract notes written by the failing agent are the least reliable diagnosis and can still
  leak identifying detail. So the class comes from the check, and the only prose comes from the
  catcher, capped and sanitized.
- Runnable evidence for a fix is built later as a **synthetic** reproduction from the lesson
  (`improvement-review/reference/eval-case-conversion.md`), never from the real case.
