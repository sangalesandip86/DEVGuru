---
name: test-repo-discovery
description: Deterministically fingerprints a repository's stack, test runners and test layout, and catalogues its fixtures, page objects, step-definition patterns and golden samples before any test is written or changed. Use first in any test-writing or suite-update task, and whenever manifests or runner configs change.
metadata:
  group: testing
  phase: 1
  binding: true
  plan-ref: "§4.13 step 1"
  stage: TEST
  inputs: []
  outputs: []
  repo_roles: [app, tests]
---

# Test Repo Discovery

## Purpose
Know the repo's real test topology *before* touching it. That means the languages, the UI
paradigm, the unit, mock, BDD and E2E runners, co-located versus mirrored layout, the naming
suffixes, the shared assets, and which existing tests are worth imitating. Scripts produce this
deterministically, at zero model tokens, and the results are recorded as FACT. An LLM
skimming a few files is not a substitute: it guesses, and its guesses aren't reproducible.

## When this applies
- Any task that creates or updates tests: [suite-authoring](../../test-implementation/suite-authoring/SKILL.md),
  [bdd-step-binding](../../test-implementation/bdd-step-binding/SKILL.md),
  [test-data-synthesis](../../test-data/test-data-synthesis/SKILL.md).
- The cached catalogue is older than the snapshot, or a manifest or runner config changed.
  Those files are an always-overlap path class (§4.5), so a change to one invalidates the cache.

## Preflight
Run the standard preflight first: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and
[`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `app` and `tests`. E2E suites often live in a separate `tests` repo,
   so fingerprint *each* resolved repo.
   - Ambiguous: raise one QUESTION listing the ranked candidates.
   - No repo at all: workspace-resolver offers local creation or a `repo-request.yaml`. Don't scaffold here.
2. **Cache check.** Reuse `.adlc/catalog/*.json` (status SATISFIED) only if it was produced at the
   current snapshot SHA and no always-overlap file has changed since. Otherwise re-run.
3. **No tests found** (`has_tests: false`). That is a finding, not a failure. Report it so the next
   skill routes to **Mode C**, which is its own `TEST_AUTOMATION` story ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)).
4. This skill needs no story or test design. It is safe to run first at any stage.

## Procedure
1. **Fingerprint the stack.** This writes `.adlc/catalog/stack.json`:
   ```bash
   python skills/testing/test-architecture/test-repo-discovery/scripts/stack_fingerprint.py <repo>
   ```
2. **Catalogue the assets.** This writes `.adlc/catalog/test-assets.json` (the full catalogue) and
   `.adlc/catalog/step-patterns.json` (phrases only). Pass CI evidence when you have it:
   ```bash
   python skills/testing/test-architecture/test-repo-discovery/scripts/test_asset_catalog.py <repo> \
     --junit reports/junit.xml --flaky reports/flaky.json --git
   ```
3. **Read the results; don't re-derive them.** Quote fields from the JSON. Don't re-open manifests to
   "double-check".
4. **Golden samples.** Take the top 2–3 per suffix group from `golden_samples`. Ranking excludes skipped,
   failing and flaky tests. It favours tests that have assertions, use shared helpers and were committed
   recently. If the top samples disagree on a convention (placement, wrapper, naming), the newest
   passing one wins. Report the conflict as an INFERENCE with both sample refs.
5. **Precedence.** Repo conventions govern *style*. Platform rules override them: no fixed sleeps, no
   real secrets or PII, no CSS/XPath for new locators, no expectations derived from code. A golden
   sample that breaks a platform rule is still a valid style reference, but **its violation is not copied**.
6. **Duplicate steps.** A non-empty `duplicate_steps` list is a pre-existing ambiguity. Record it as a
   RISK, and don't add a third definition.
7. **Hand off.** Record the catalogue paths as `repo@sha:path` plus content hash for the handoff (§4.7).

## Outputs
| Artifact | Classification | Who may read it |
|---|---|---|
| `.adlc/catalog/stack.json` | FACT (script output, hook-recorded) | all roles |
| `.adlc/catalog/test-assets.json` | FACT | test-engineer, qa-diagnose, developer |
| `.adlc/catalog/step-patterns.json` | FACT, phrases only: keyword and pattern, with no paths, line numbers or step bodies | **also qa-derive**. It is the only catalogue file that lets a code-blind designer reuse existing step phrasing. |
| Convention conflicts | INFERENCE | |
| Duplicate step definitions | RISK | |

## Enforcement
- FACT entries are written by the PostToolUse fact-writer hooks, not by the model (§5.6 row "FACT entries are grounded").
- qa-derive's denied-path list blocks `test-assets.json` and every implementation path.
  `step-patterns.json` is explicitly readable. Enforcement comes from role tool scoping (`skills/roles/qa-derive/role.yaml`).
- Everything else in this skill is guideline only. Choosing the right samples is checked indirectly by
  [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py)
  and [no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py).

## References
- [reference/discovery-outputs.md](reference/discovery-outputs.md): field-by-field output contract
- [scripts/stack_fingerprint.py](scripts/stack_fingerprint.py), [scripts/test_asset_catalog.py](scripts/test_asset_catalog.py), [scripts/test_discovery.py](scripts/test_discovery.py)
- [suite-authoring](../../test-implementation/suite-authoring/SKILL.md), [bdd-feature-authoring](../../test-design/bdd-feature-authoring/SKILL.md)
- [flaky-test-intelligence](../../test-maintenance/flaky-test-intelligence/SKILL.md)
- Plan §4.13, [ADR 0003](../../../../docs/adr/0003-test-engineering-and-data.md)
