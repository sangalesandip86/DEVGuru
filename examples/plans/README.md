# Worked example: intraday portfolio VaR

This is a small `plans/` tree that runs end to end through the planning gates
(plan v3.1 §4.12). Its expected output is checked by `WorkedExampleTest` in
`skills/enforcement/ci-checks/planning-gates/tests/test_planning_gates.py`.

```
requirements/REQ-1.yaml   real-time portfolio risk monitoring
epics/EPIC-1.yaml         intraday VaR for PMs (features FEAT-1 API, FEAT-2 tile)
milestones/MS-1.yaml      "PMs see intraday VaR for equity books" (outcome, time axis)
stories/ST-1.yaml         FEATURE_STORY   VaR tile on the dashboard (ui)
stories/ST-2.yaml         API_CONTRACT    GET /v1/portfolios/{id}/var
stories/ST-3.yaml         SPIKE           parametric vs historical VaR latency
stories/ST-4.yaml         TECHNICAL_STORY follow-up of the spike, still in draft
evidence/evidence.json    sample SYSTEM evidence export (ledger + forge/CI events)
evidence/tests, junit.xml sample tagged tests and results for ac_coverage.py
```

## Run it

```bash
G=skills/enforcement/ci-checks/planning-gates
E=examples/plans
python $G/plan_lint.py $E --readiness $E/evidence/evidence.json
for s in ST-1 ST-2 ST-3 ST-4; do python $G/readiness_gate.py --plans $E --story $s --evidence $E/evidence/evidence.json --now 2026-10-20T09:00:00Z; done
python $G/ac_coverage.py --tests $E/evidence/tests --junit $E/evidence/junit.xml --plans $E --story ST-1 > cov.json
python $G/completion_gate.py --plans $E --story ST-1 --evidence $E/evidence/evidence.json --coverage cov.json --now 2026-10-20T09:00:00Z
python $G/completion_gate.py --plans $E --story ST-3 --evidence $E/evidence/evidence.json --now 2026-10-20T09:00:00Z
```

## Expected output (verified)

**plan-lint:** 1 requirement, 1 epic, 4 stories and 1 milestone. No errors, no warnings and no AC-freeze violations. Exit code 0.

**Readiness gate**

| Story | Effective tier (sources) | Result | Why |
|---|---|---|---|
| ST-1 | MEDIUM (path) | **READY** | Every applicable item passes, including qa-derive testability and developer feasibility reviewed against the current AC hash |
| ST-2 | HIGH (type floor `API_CONTRACT` + `openapi.yaml` path) | **NOT_READY** | Three items fail (see below) |
| ST-3 | LOW (`docs/adr/**`) | **READY** | Spike variant: question and time-box stated, developer feasibility reviewed |
| ST-4 | MEDIUM (path) | **NOT_READY** | Seven items fail (see below) |

ST-2 fails on:
- `qa_testability`: the only record is a SYSTEM/VERIFIED "all AC have G/W/T" check. **Structural evidence never satisfies a JUDGMENT.**
- `architect_contract_review`: missing.
- `scope_approval`: needs `human:product-owner` at HIGH.

ST-4 fails on:
- an UNRESOLVED dependency on the position feed;
- an OPEN blocking QUESTION;
- no negative AC;
- no `no-behaviour-change` AC (TECHNICAL_STORY);
- no security considerations (CONFIDENTIAL data);
- no qa-derive review;
- no developer review.

**ac-coverage (ST-1)**
- AC-1 and AC-3 are covered through IDs in the test titles. AC-2 is covered through an `// @ac` comment.
- All three pass.
- AC-4 is `manual`, so it is not expected in test results.
- 1 untagged test.

**Completion gate**

| Story | Variant | Result |
|---|---|---|
| ST-1 | standard | **DONE**, `awaiting_acceptance: true`. Every DONE item passes: Change Set CS-11 INTEGRATED; automated AC passing; the manual AC verified by qa-diagnose; `ci`, `unit-tests`, `secret-scan` and `accessibility` VERIFIED; code-reviewer ACCEPT; diff within `affected_paths`. As a MEDIUM `FEATURE_STORY`, it reaches **ACCEPTED** only after a `human:product-owner` approval event for `po_acceptance`. |
| ST-3 | spike | **DONE**. A DECISION with a merged ADR, follow-up ST-4 exists, and the merged change touched only `docs/adr/`. No acceptance step applies, so DONE is terminal. |

## Things to try

- Edit a `then:` in `stories/ST-1.yaml` and re-run plan-lint. ST-1 is reported `REQUIRES_REFINING`. Readiness then shows qa-derive and developer reviews as *stale AC hash*, and completion fails `ready_at_current_ac`.
- Add `status: READY` to any story. The schema rejects it, because status is derived and never stored.
- Change ST-1's `size` to `L`. `size_ok` FAILs, and the story must be split.
- Add `src/engine/fast.py` to CS-13's `changed_paths`. The spike FAILs `spike_no_production_code`.
