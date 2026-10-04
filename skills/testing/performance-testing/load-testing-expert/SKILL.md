---
name: load-testing-expert
description: Design and run load/stress/soak tests with k6 or JMeter against SLO thresholds. Use when a change can affect throughput or latency.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [test-design, nfr-catalog]
  outputs: [test-suite]
  repo_roles: [app, tests, infra]
---

# Load Testing Expert


## Purpose
Answer "will it hold at the load we actually expect?" with numbers, not intuition.

## When this applies
- Change touches hot paths, queries, caching, connection pools, serialization, or infrastructure sizing.
- Architect's design cites a scale target (QPS, data volume) that needs proving.
- CRITICAL-tier release requiring staged rollout.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests, infra]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Numeric targets and environment.** The NFR AC state numbers (p95, RPS, error rate), and a load-target environment sized like production is resolved. Load against shared or production environments is scheduled only by CI or a human.

Never proceed on a missing input silently.

## Procedure
1. **Workload model from evidence**: request mix, arrival rate, payload sizes, and think time taken from
   production metrics/logs (cite the dashboard query and date). No data → `ASSUMPTION` with expiry, and
   say so in the report.
2. **Pick the test type**:
   | Type | Shape | Question it answers |
   |---|---|---|
   | Load | Ramp to expected peak, hold | Does it meet SLOs at peak? |
   | Stress | Ramp past peak until failure | Where and how does it break? |
   | Soak | Expected load for hours | Leaks, connection exhaustion, GC drift? |
   | Spike | Sudden jump and drop | Autoscaling and queueing behavior? |
3. **Open model for user-facing APIs** (arrival-rate executors) — closed models hide latency under
   saturation (coordinated omission).
4. **Thresholds = SLOs**, so the run itself passes or fails: e.g. `p(95)<300`, `p(99)<800`, error rate `<0.1%`.
5. **Environment**: production-like sizing, isolated from other load, realistic data volume. Never against
   production without a human-approved plan — that is an `EXTERNAL_MUTATION` the agent can't perform.
6. **Load generator health**: watch generator CPU/network; an overloaded generator produces fake latency.
7. Compare against the stored baseline via [`../perf-baseline-tracker/SKILL.md`](../perf-baseline-tracker/SKILL.md);
   investigate regressions with [`../bottleneck-analysis/SKILL.md`](../bottleneck-analysis/SKILL.md).

Tool recipes: [`reference/k6-scripts.md`](reference/k6-scripts.md), [`reference/jmeter-scripts.md`](reference/jmeter-scripts.md).

## Outputs
- Scripts (`REPO_WRITE`). Threshold pass/fail from a CI-run test → `VERIFIED`.
- Capacity conclusions → `INFERENCE` citing run results; workload model → `ASSUMPTION`s with sources.

## Enforcement
**Enforced** (partial) — see rules below.

Threshold results are machine evidence. Running against production is blocked by operation-class scoping (plan §4.5).

## References
- [`reference/k6-scripts.md`](reference/k6-scripts.md)
- [`reference/jmeter-scripts.md`](reference/jmeter-scripts.md)
- [`../../../engineering-design/scale-readiness-reviewer/`](../../../engineering-design/scale-readiness-reviewer/)
