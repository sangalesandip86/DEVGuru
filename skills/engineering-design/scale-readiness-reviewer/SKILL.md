---
name: scale-readiness-reviewer
description: Review scale readiness -- capacity, bottlenecks, failure under load. Use before launches, traffic events, or HIGH/CRITICAL changes.
metadata:
  group: engineering-design
  phase: progressive
  binding: false
  plan-ref: "§4.9"
  stage: ARCHITECTURE
  inputs: [architecture-package, nfr-catalog]
  outputs: [review-verdict]
  repo_roles: [app, infra]
---

# Scale Readiness Reviewer


## Purpose

Answer "will this hold at the expected load, and fail gracefully above it?" with evidence.
Load-test results are machine evidence (`VERIFIED` comes from the test runner via the server);
this skill's judgment over them is `REVIEWED`.

## When this applies

- A launch, campaign, migration, or seasonal peak with a stated load target.
- A HIGH/CRITICAL Change Set on a user-facing hot path.
- Request: "are we ready for N× traffic?"

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Primary stage ARCHITECTURE (review of the proposed design); also REVIEW for HIGH+ Change Sets.

- **Inputs:** the architecture package and the NFR catalog's numeric targets.
- **BACKFILL:** no architecture package → propose `BACKFILL: ARCHITECTURE`.
- **Repo roles:** `app`, `infra` (existing deployment and capacity config).

## Existing project standards
On an existing repo, load [project-conventions](../project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Scaling recommendations reuse the project's existing infrastructure and libraries unless the NFR numbers show they can't meet the target.

## Procedure

1. **Fix the target.** Required: peak QPS (or concurrent users), data volume, p99 latency
   target, error-rate budget, and duration of peak. No target → blocking `QUESTION`; a
   readiness review without a number cannot pass.
2. **Gather evidence** (cite each as FACT from the ledger or attach):
   - Current production metrics at recent peak (utilization, p99, error rate).
   - Load-test results against the target (`../../testing/performance-testing/load-testing-expert/`).
   - Baseline comparison (`../../testing/performance-testing/perf-baseline-tracker/`).
3. **Walk the checklist** below. Each item: PASS (with source) / FAIL (with source) / UNKNOWN.
   UNKNOWN on a critical item resolves toward scrutiny (§5.3) — treat as FAIL.
4. **Decide.** `REJECT` if any critical item FAILs; otherwise `ACCEPT` with listed `RISK`s.

## Checklist

| # | Item | Critical |
|---|---|---|
| 1 | Load test reached ≥ 1.5× target peak for ≥ the peak duration | Yes |
| 2 | p99 latency at target within SLO | Yes |
| 3 | Headroom ≥ 30% on CPU, memory, connections, DB IOPS at target | Yes |
| 4 | Bottleneck identified (the first resource to saturate is known) | Yes |
| 5 | Autoscaling tested: scale-out time < time-to-saturation of a burst | Yes |
| 6 | Every outbound call has a timeout, retry budget, and circuit breaker | Yes |
| 7 | Load shedding / rate limiting defined above capacity (graceful degradation) | Yes |
| 8 | Downstream dependencies confirmed capacity for their share of load | Yes |
| 9 | Queues have lag alerts and DLQs | No |
| 10 | Caches: hit-rate measured; stampede protection | No |
| 11 | Dashboards + alerts for the four golden signals | Yes |
| 12 | Runbook and rollback/feature-flag kill switch tested | Yes |
| 13 | Data growth: storage at 24 months fits, with partition/retention plan | No |
| 14 | Quotas and external rate limits (cloud, third-party APIs) checked | No |

## Outputs

- `DECISION` (`REVIEWED`, ACCEPT/REJECT) referencing each checklist result.
- `RISK` per FAIL/non-critical gap; `QUESTION` per missing target or evidence.

## Enforcement
**Guideline only** — no enforcement point yet.


- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Load-test pass/fail becomes `VERIFIED` only via server ingestion of CI/test-runner output (§5.5).
- Checklist completion: **guideline only — no enforcement point yet**.

## References

- `../system-architect/reference/scaling-playbook.md`
- `../code-design-reviewer/reference/performance-checklist.md`
- `../../testing/performance-testing/bottleneck-analysis/`
