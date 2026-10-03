---
name: bottleneck-analysis
description: Locates the cause of a performance regression or saturation point using the USE and RED methods, profiling, traces, and query analysis, producing evidence-cited root-cause hypotheses. Use after a load test misses its thresholds or a latency regression is detected.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: REVIEW
  inputs: [test-suite]
  outputs: [review-verdict]
  repo_roles: [app, infra]
---

# Bottleneck Analysis

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Find *where* the time goes, with evidence, before anyone changes code to "optimize" it.

## When this applies
- A load test missed its thresholds, perf-baseline-tracker flagged a regression, or production latency rose.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, infra]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`.
2. **Inputs** `[test-suite]`. Each resolves to one of:
   - SATISFIED;
   - ADOPT: it exists outside the platform, so import it as DRAFT with its source trust level;
   - BACKFILL: propose the smallest upstream run that produces it;
   - ASK: one batched QUESTION, never empty-handed;
   - BLOCK: a gate failed on existing evidence.
3. **Evidence.** A failed or regressed load or performance run with metrics, traces or profiles attached. Without them, raise a QUESTION about the missing telemetry instead of forming hypotheses.

Never proceed on a missing input silently.

## Procedure
1. **Frame**: which scenario, which metric, since which commit/snapshot. Cite the run.
2. **RED per service** (Rate, Errors, Duration) from traces/metrics to find the slowest hop. Use distributed
   traces (OpenTelemetry) — the critical path span tells you which service and which call.
3. **USE per resource** in that service (Utilization, Saturation, Errors): CPU, memory/GC, threads/connection
   pools, DB connections, disk I/O, network, queue depth, locks.
4. **Drill down by suspect**:
   | Suspect | Evidence to gather |
   |---|---|
   | CPU-bound code | Flame graph (async-profiler, py-spy, pprof, dotnet-trace) under load |
   | Database | Slow query log, `EXPLAIN (ANALYZE, BUFFERS)`, N+1 detection, lock waits, index usage |
   | Pool exhaustion | Pool wait time/active count metrics (HikariCP, pgbouncer) |
   | GC / memory | GC logs, pause times, allocation rate, heap after GC trend |
   | Downstream | Span latency of outbound calls, retries, timeouts, circuit-breaker state |
   | Contention | Thread dumps, lock profiling, `pg_stat_activity` wait events |
5. **Hypothesis → confirm**: each hypothesis is an `INFERENCE` citing specific evidence entries. Confirm with
   a targeted experiment (one change, re-run the same scenario) before calling it the root cause.
6. Coordinate with qa-diagnose: it has the read access to logs, traces, and metrics this needs (plan §4.7).

## Outputs
- Profiles, query plans, metrics excerpts → `FACT`. Root-cause hypotheses → `INFERENCE`; confirmed after the
  experiment's CI run → `VERIFIED` for the measured improvement, `REVIEWED` for the diagnosis.

## Enforcement
Guideline only — no enforcement point yet.

## References
- [`../perf-baseline-tracker/SKILL.md`](../perf-baseline-tracker/SKILL.md)
- [`../../../roles/qa-diagnose/`](../../../roles/qa-diagnose/)
- [`../../../engineering-design/code-design-reviewer/reference/performance-checklist.md`](../../../engineering-design/code-design-reviewer/reference/performance-checklist.md)
