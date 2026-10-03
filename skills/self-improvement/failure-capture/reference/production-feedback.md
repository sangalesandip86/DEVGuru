# Production Feedback

A production incident, rollback, or performance regression linked to a Change Set feeds back
in **two separate places**:

| Where | What | Leaves the project? |
|---|---|---|
| Project Evidence Ledger | A new correcting entry: `outcome_status: CHALLENGED`, `parent_entry_id` = the original entry, `classification: INFERENCE` for the hypothesized root cause, explicitly unconfirmed, `signal_source: PRODUCTION` | **Never** |
| Incident table | A `production` incident: pointers (`evidence_refs`) + `check_id` + `failure_class` + skill/step | Only as a count inside a sanitized lesson |

## Rules
1. **Append-only.** Never retag or mutate the original entry. The correction is a new entry
   written with `mcp:adlc.record_correction` (§4.3).
2. **The hypothesis stays local.** The root-cause INFERENCE (which service, which query, which
   customer was affected) lives only in the project ledger. The incident never copies it.
3. **Pointers + class only.** The incident's `evidence_refs` point at the correcting entry and
   the production FACT entries (deploy event, alert, metric). `check_id` is
   `production:incident`, `production:rollback`, or `production:perf_regression`, all mapping to
   `INCORRECT_BEHAVIOR`. A responder who knows the real cause sets a more specific class
   (for example `MISSING_SAFEGUARD` when the rollback plan was missing) and writes a sanitized
   note, as for any judgment-only failure.
4. **Skill and step.** Name the skill step whose output is implicated (for example the
   developer's implementation step, or code-reviewer's review step if it accepted the defect).
   If that isn't known yet, record the incident against the reviewing skill's verdict step and
   let the post-incident review add a corrected incident (`parent_incident_id`).
5. `ROLLED_BACK` is ingested from the forge/CI event. This skill does not set it.

## Example

Local ledger (never shared):
```yaml
- entry_id: ENTRY-c2e81f07aa31
  parent_entry_id: ENTRY-9990b3d1c2f4      # code-reviewer REVIEWED: ACCEPT
  outcome_status: CHALLENGED
  classification: INFERENCE
  signal_source: PRODUCTION
  content: "Hypothesis (unconfirmed): p95 regression after release caused by N+1 query in the list endpoint"
  input_references: [ENTRY-5a1d0e2b7c90, ENTRY-77f0c4d9e1ab]
```

Incident (pointers + class):
```json
{"signal_type": "production", "signal_source": "PRODUCTION", "check_id": "production:perf_regression",
 "failure_class": "INCORRECT_BEHAVIOR", "skill": "roles/code-reviewer", "step": "Procedure 3 — review performance",
 "evidence_refs": ["ENTRY-c2e81f07aa31", "ENTRY-5a1d0e2b7c90"], "...": "..."}
```
