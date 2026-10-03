# Sizing guide

Agents do not produce story points or velocity. Story points are a team-relative commitment
tool. An agent's estimate in points is uncalibrated, and the planning layer does not do
capacity planning (ADR 0002). Size is a **PROPOSAL about the predicted diff**. It is measured
against the change-size cap from plan §7, which is in
[`path-tiers.json`](../../../change-management/risk-tiering/path-tiers.json) under
`diff_size_cap`: by default 400 changed lines or 25 files per Change Set.

| Size | Predicted changed lines (incl. tests) | Repos | Typical shape |
|---|---|---|---|
| `XS` | ≤ 50 | 1 | copy change, config flag, single-function fix |
| `S` | ≤ 150 | 1 | one endpoint or component with its tests |
| `M` | ≤ 400 (the cap) | 1–2 | a vertical slice across 2–3 modules |
| `L` | > 400, **or** > 2 repos, **or** > 25 files | any | **must be split before READY** (DoR `size_ok`) |

Record the basis so it can be calibrated later:

```yaml
size: S
size_basis:
  predicted_changed_lines: 140
  repos: 1
```

## How to predict
1. List the modules in `affected_paths` (from the dependency-discovery scanners, not memory).
2. For each module, estimate the production lines and the test lines. Test code is usually 1–1.5× the production change.
3. Add the migrations, contract specs and docs the story's type requires.
4. If the estimate is near a boundary, pick the larger size.

## Calibration (self-improvement)
At DONE, the completion gate has the actual `changed_lines` from the linked Change Sets.
Predicted versus actual is recorded and feeds:
- the **size-calibration** pilot metric (plan §7);
- a self-improvement signal when the planner consistently under-predicts. Repeated `M`s that land above 400 lines trigger an improvement review of this guide.

## Splitting an `L`
Use the [slicing patterns](../../epic-decomposer/reference/slicing-patterns.md). In order of preference:
1. split by **workflow step**;
2. split by **business rule or variation**;
3. split by **data subset**;
4. take a **SPIKE** for the unknown part.

Never split by technical layer, unless each part is a typed `TECHNICAL_STORY` with its own
`no-behaviour-change` criterion.
