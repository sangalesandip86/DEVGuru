---
name: deployment-verification
description: Define post-deploy checks -- smoke tests, security headers, DAST baseline, canary health. Use when planning a release or rollback.
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.8, §5.10, §4.5"
  stage: TEST
  inputs: [change-set]
  outputs: [test-suite]
  repo_roles: [app, infra]
---

# Deployment Verification


## Purpose
Prove that what was deployed is what was approved, and that it behaves and is configured safely in the
target environment. `RELEASED` is an observed deployment record plus an environment approval (plan §5.10);
this skill defines the checks that make that record trustworthy.

## When this applies
- Any Change Set reaching `INTEGRATED → RELEASED`; mandatory for CRITICAL staged rollouts.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, infra]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Deploy record.** There is an observed deployment record for the environment (a forge or CI event). Checks run in CI after the deploy: agents author checks but never run them against shared environments.

Never proceed on a missing input silently.

## Procedure
Agents **design** these checks; **CI runs them** after deploy. `DEPLOY` and `EXTERNAL_MUTATION` operation
classes are never available to agents (plan §4.5).

1. **Identity of the artifact**: deployed image digest / build SHA matches the one recorded for the Change Set
   (and, where available, its signature/provenance attestation). Mismatch = stop.
2. **Smoke tests**: a few critical-journey checks against the environment (Newman, k6 with `vus: 1`, Playwright
   `@smoke` tag). Read-only or using dedicated test accounts.
3. **Security posture checks**:
   - TLS and headers: HSTS, CSP, `X-Content-Type-Options`, cookie flags (`Secure`, `HttpOnly`, `SameSite`);
   - no debug endpoints, stack traces, directory listings, default credentials, or admin consoles exposed;
   - DAST baseline: `zap-baseline.py -t $URL -r zap.html -J zap.json` (passive; full active scans only in non-prod);
   - config drift: deployed config matches IaC (`terraform plan -detailed-exitcode` shows no drift).
4. **Canary / staged rollout gates**: compare canary vs baseline on error rate, p95 latency, saturation for a
   fixed window (Argo Rollouts / Flagger analysis templates). Pre-define abort thresholds.
5. **Rollback criteria written before deploy**; automatic rollback on gate failure. A rollback moves the Change
   Set to `ROLLED_BACK` and writes a production-feedback entry (CHALLENGED, referencing the original — never editing it).
6. **Record**: CI calls the deployment record path (`record_deployment` for contract compatibility; forge
   deployment status for `RELEASED`), under the CI identity.

## Outputs
- Check results from CI → `VERIFIED`; deployment record + environment approval → `RELEASED` (server-observed).
- Check design → `PROPOSAL`/`REVIEWED`. Failures → `RISK` and production-feedback entries.

## Enforcement
**Enforced** (partial) — see rules below.

Post-deploy gates run in CI/CD (deterministic); `RELEASED` is server-internal from forge/CI events (plan §5.6 row 1, §5.10).

## References
- [`../../api-contract-testing/postman-newman/SKILL.md`](../../api-contract-testing/postman-newman/SKILL.md)
- [`../../../change-management/change-set/reference/approval-matrix.md`](../../../change-management/change-set/reference/approval-matrix.md)
- [`../../../self-improvement/failure-capture/reference/production-feedback.md`](../../../self-improvement/failure-capture/reference/production-feedback.md)
