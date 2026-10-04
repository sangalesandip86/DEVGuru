---
name: autonomy-gating
description: Set agent autonomy level based on measured verification strength. Use before starting repo work or deciding on per-change human review.
metadata:
  group: governance
  phase: 1
  binding: true
  plan-ref: "§4.11, §7"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: [app]
---

# Autonomy Gating

## Purpose
`VERIFIED` is only as trustworthy as the tests behind it. A repo with weak or absent tests
starts in **assist mode** regardless of computed risk tier; autonomy rises only as the repo's
own measured verification strength rises.

## When this applies
- At the start of every Change Set — read the repo's current autonomy level.
- When a LOW/MEDIUM change would otherwise merge on `VERIFIED` alone.
- Periodically (weekly in a pilot), to recompute levels from ledger and CI data.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md) (cross-cutting).

- **Inputs:** each `app` repo's measured verification strength (CI reliability, changed-code coverage, mutation score).
- **ADOPT/create:** a newly adopted or newly created repo has no history, so it starts in assist mode.
- **Repo roles:** `app`.

## Procedure
1. Compute the repo's verification strength from
   [verification-strength.md](reference/verification-strength.md).
2. Map it to an autonomy level (`ASSIST`, `SUPERVISED`, `AUTONOMOUS_LOW`).
3. Apply the stricter of: autonomy-level requirement, risk-tier approval matrix
   (`../../change-management/change-set/reference/approval-matrix.md`).
4. If strength can't be computed (no CI data), use `ASSIST` — fail-safe default (§5.3).
5. Record the level used as a `DECISION` entry citing the metrics it was based on.

## Outputs
- `DECISION` (autonomy level + metric sources), `RISK` when a repo is downgraded.

## Enforcement
**Guideline only** — no enforcement point yet.

Guideline only — no enforcement point yet. Target enforcement: branch ruleset requiring
human review in `ASSIST` repos, configured from the computed level.

## References
- [reference/verification-strength.md](reference/verification-strength.md)
- `../../../docs/pilot-measurement.md`
- `../../self-improvement/failure-capture/SKILL.md` (unverified-positive tagging uses the same signal)
