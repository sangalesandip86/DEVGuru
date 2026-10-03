---
name: perf-baseline-tracker
description: Stores performance baselines per endpoint/scenario and compares new load or benchmark runs against them with noise-aware regression thresholds. Use after any load test or micro-benchmark run, or when asked whether a change made something slower.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8, §7"
  stage: TEST
  inputs: [test-suite]
  outputs: [review-verdict]
  repo_roles: [app, infra]
---

# Performance Baseline Tracker

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Turn individual performance runs into a regression signal. A single run's p95 means little without
a baseline and an understanding of run-to-run noise.

## When this applies
- A load test or benchmark completed (k6 `summary.json`, JMeter `statistics.json`, JMH, pytest-benchmark,
  BenchmarkDotNet, Go `-bench` output).
- A production performance regression is linked to a Change Set — that becomes a production signal for
  self-improvement (plan §4.2).

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, infra]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Baseline.** A recorded baseline exists for the same scenario, environment class and dataset size. If there is none, the first run *creates* the baseline and asserts nothing.

Never proceed on a missing input silently.

## Procedure
1. **Baselines are pinned**: each baseline records commit SHA, environment spec, tool version, workload
   model version, and date. Store them as versioned JSON in the repo (e.g. `perf/baselines/<scenario>.json`)
   or a metrics store — never "whatever ran last".
2. **Measure noise**: run the baseline ≥ 3 times; record median and spread per metric.
3. **Compare** the candidate run per scenario and metric (p50, p95, p99, throughput, error rate):
   - regression = candidate worse than baseline by more than `max(threshold, 2 × observed spread)`;
   - default thresholds: p95 +10%, p99 +15%, throughput −5%, any error-rate increase above 0.1 pp;
   - for micro-benchmarks use the tool's statistical comparison (`benchstat`, JMH confidence intervals).
4. **Apples to apples**: refuse the comparison (and record a `QUESTION`) if environment, data volume, or
   workload model differ from the baseline.
5. **Updating a baseline** after an intended change is a `PROPOSAL` that needs reviewer acceptance, with the
   justification cited — never automatic.

## Outputs
- Comparison numbers → `FACT` (hook-recorded tool output). Regression verdict from a deterministic CI
  comparison step → `VERIFIED`. Explanations → `INFERENCE`. Baseline change → `PROPOSAL`.

## Enforcement
Guideline only — no enforcement point yet, until the comparison runs as a CI step that fails on regression.

## References
- [`../load-testing-expert/SKILL.md`](../load-testing-expert/SKILL.md)
- [`../bottleneck-analysis/SKILL.md`](../bottleneck-analysis/SKILL.md)
- [`../../../self-improvement/failure-capture/reference/production-feedback.md`](../../../self-improvement/failure-capture/reference/production-feedback.md)
