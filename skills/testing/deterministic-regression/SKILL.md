---
name: deterministic-regression
description: Model-free golden evaluation suite for deterministic replay of platform behavior (risk routing, role assignment, gate checks).
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.9"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Deterministic Regression Suite

## Purpose
Model-free golden evaluation suite that replays recorded platform scenarios through real
engines to verify deterministic behavior. No LLM involved — pure function-level replay.

## When this applies
On every PR touching `skills/` or MCP server code. CI runs the full suite.

## Procedure
1. Author golden cases as JSON files in `golden-cases/`.
2. Run `python scripts/replay_runner.py golden-cases/` to replay all cases.
3. Each case declares fixture data, a sequence of steps, and expected outputs.
4. Steps invoke platform functions (risk scoring, role routing, gate evaluation) with
   the fixture data and compare outputs against expected values.

## Constraints
- No model involved — pure deterministic replay
- Max fixture size: 256 KB
- Max steps per case: 80
- Max cases in suite: 500
- Cases are version-controlled alongside the skill code

## Check Catalog
See [reference/check-catalog.md](reference/check-catalog.md) for the full list of
deterministic checks.

## Enforcement
**Guideline** — runs in CI via `python -m unittest discover`.

| Rule | Enforced by |
|---|---|
| Suite passes on PR | CI check |
| Skill revisions must pass suite before REVIEWED | Guideline |

## References
- [reference/suite-format.md](reference/suite-format.md)
- [reference/check-catalog.md](reference/check-catalog.md)
