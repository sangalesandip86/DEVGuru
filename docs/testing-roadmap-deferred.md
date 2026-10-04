# Deferred Testing Layers — C (Prompt Regression)

Layer F (Composition) has been implemented — see `skills/testing/composition-tests/`.
Layer C (Prompt Regression) remains deferred for decision.

---

## Layer C: Prompt Regression Testing

**Problem:** Skills produce different outputs when the underlying model changes (Sonnet 4 →
Sonnet 5, Opus version bumps) or when skill text is edited. Without regression baselines,
regressions are invisible until a user reports a broken pipeline.

**Industry references:** Promptfoo, LangSmith, Braintrust, Anthropic internal eval framework.

### C.1 Output Fingerprinting

Run each skill with a fixed input and capture a **structural fingerprint** — not exact text,
but the shape of the output:

```yaml
# Example fingerprint for story-writer
fields_present: [id, title, type, objective, persona, acceptance_criteria, nfrs, tier_floor]
ac_count: 4
nfr_refs_resolved: true
type_in_enum: true
tier_floor_matches_type: true
sections: [Objective, Persona, Value, AC, NFRs, Touches]
```

A CI job compares the current fingerprint to the baseline. Structural changes (missing field,
new section, changed enum) fail the check. Text changes within the same structure are logged
but don't fail.

**Baseline workflow:**
1. Pin a model version (e.g., `claude-sonnet-4-20250514`).
2. Run the eval set → save fingerprints as `baselines/<skill>/<model>.fingerprint.json`.
3. On model upgrade or skill edit, re-run → diff fingerprints.
4. Promote the new fingerprint to baseline after human review.

### C.2 Behavioral Invariants

Properties that must hold regardless of model version:

| Invariant | Skill | Check |
|---|---|---|
| Never sets status field | story-writer | `"status" not in output` |
| Never references implementation files | qa-derive | no `src/`, `lib/`, `app/` paths in output |
| Unknown path → HIGH | risk-tiering | `assert tier != "LOW" when path not in tiers` |
| FACT never from agent | evidence-gate | `source_type in hook_sources` |
| AC IDs match pattern | story-writer | `re.match(r"ST-\d+/AC-\d+", ac_id)` |
| Tier floor from story type | story-writer | `tier >= TYPE_FLOORS[story_type]` |

### C.3 Cross-Model Testing

Same eval set on Sonnet, Opus, Haiku. Structural assertions must pass on all. Quality rubric
scores can vary — log them as trends:

```
Model       story-writer  qa-derive  architect  risk-tiering
sonnet-4    92/100        88/100     90/100     100/100
opus-4      95/100        91/100     94/100     100/100
haiku-4.5   85/100        82/100     86/100     100/100
```

Deterministic skills (risk-tiering, skill-router) should score 100 on all models.

### C.4 Drift Detection (Weekly CI)

```yaml
# .github/workflows/prompt-regression.yml
schedule:
  - cron: "0 6 * * 1"  # Monday 6am
jobs:
  regression:
    steps:
      - run: python skills/testing/eval-harness/eval_runner.py --suite all --model $MODEL
      - run: python skills/testing/eval-harness/compare_baselines.py --report
      - uses: actions/upload-artifact@v4
        with: { path: eval-report.json }
```

### C.5 Cost Estimate

- ~9 mandatory skills × 3-5 eval cases × 3 models = 80-135 LLM calls per run
- At ~$0.01-0.05 per call = $1-7 per weekly run
- Baseline creation: one-time ~$5-15

### C.6 Implementation Steps

1. Build `eval_runner.py` with `--skill`, `--input`, `--model` flags
2. Create 3-5 canned inputs per mandatory skill
3. Write structural assertion schemas per skill
4. Generate initial baselines on pinned model
5. Add `compare_baselines.py` with diff reporting
6. Wire into weekly CI

---

## Layer F: Composition / Emergent Behavior Testing — IMPLEMENTED

> **Status:** Implemented in `skills/testing/composition-tests/` (29 tests, canned + live modes).
> Run: `python -m unittest skills/testing/composition-tests/test_composition.py -v`

**Problem:** Individual skills pass their tests but the pipeline breaks when they compose.
Information degrades at handoffs (telephone game), token budgets overflow, skills produce
contradictory evidence, and failure cascades aren't handled.

**Industry references:** SWE-bench (single-agent), GAIA (multi-step reasoning), WebArena
(agent interaction), Anthropic multi-agent eval framework, Google Gemini agent benchmarks.

### F.1 Mandatory + Advisory Skill Interaction

When skill-router binds multiple skills to the same stage, test:

| Scenario | Skills loaded | Check |
|---|---|---|
| API feature story | story-writer + contract-registry + schema-validation | No conflicting AC about API shape |
| Security story | story-writer + trust-boundaries + secret-scanning | Security AC doesn't duplicate trust-boundary rules |
| Data migration | story-writer + change-set + risk-tiering | Tier floor escalation is consistent |
| Full TEST stage | suite-authoring + bdd-step-binding + playwright-expert | Test file paths don't collide, frameworks don't conflict |

Test approach: load all bound skills' outputs for the same story, check for:
- Field conflicts (same field, different values)
- Classification conflicts (same evidence, different classifications)
- Token budget (combined skill text + reference text < context limit)

### F.2 Role Handoff Chains

Full pipeline simulation with canned data:

```
Scenario: "Add payment endpoint"

INTAKE: requirement-intake → requirement.yaml
  ↓ handoff to architect
ARCHITECTURE: system-architect → architecture-package/
  ↓ handoff to product-planner
PLAN: story-writer → ST-1.yaml (FEATURE_STORY, tier HIGH)
  ↓ qa-derive reads story (NOT code)
TEST design: test-case-design → test-designs/ST-1.yaml
  ↓ handoff to developer
IMPLEMENT: change-set → code changes
  ↓ handoff to test-engineer
TEST bind: suite-authoring → test files
  ↓ handoff to code-reviewer
REVIEW: code-design-reviewer → verdict
  ↓ handoff to security-reviewer
REVIEW: trust-boundaries → security verdict
```

At each handoff, assert:
- **Traceability**: can trace back to the requirement (REQ-n → EPIC-n → ST-n → CS-n)
- **Evidence completeness**: all required classifications present (FACT, DECISION, REVIEWED)
- **No information loss**: key fields from upstream appear in downstream inputs
- **Authority preservation**: REVIEWED from correct role, VERIFIED from system only

### F.3 Failure Cascade Testing

| Failure point | Expected cascade | Test |
|---|---|---|
| architect skill fails at ARCHITECTURE | developer gets BLOCK at preflight | Simulate empty architecture-package, assert preflight BLOCK |
| qa-derive produces empty test design | test-engineer gets BACKFILL, not silent proceed | Assert suite-authoring preflight returns BACKFILL |
| risk-tiering disagrees with path_tier_lookup | effective_tier = max(both) | Inject disagreement, assert max() applied |
| snapshot stale at REVIEW | code-reviewer gets STALE, handoff blocked | Advance HEAD, assert validate_snapshot_currency catches it |
| 3rd REJECT from code-reviewer | escalation to human:tech-lead | Already tested; extend to verify pipeline halts |

### F.4 Scaling Tests

```
Scenario: "50-story epic in monorepo with 12 packages"

Inputs:
  - epic with 50 user stories across 12 workspace packages
  - stack.json with 12 package entries
  - 200+ changed files across packages

Checks:
  - Workspace walker finds all 12 packages
  - Skill router binds correct per-package skills
  - Parallel execution respects dependency graph
  - Change sets don't share worktrees
  - Total token budget stays within limits
  - Pipeline completes without OOM or context overflow
```

### F.5 Cost Estimate

- Full pipeline simulation: 20-50 LLM calls per scenario
- 5 scenarios × 50 calls × $0.03 avg = $7.50 per run
- Scaling test: ~200 calls = ~$6
- Total: ~$15-25 per full composition test run
- Run: weekly or on significant skill changes

### F.6 Implementation (Done)

Implemented as:
- `skills/testing/composition-tests/pipeline_simulator.py` — canned mode default, live mode opt-in via `ADLC_LIVE_MODE=1`
- `skills/testing/composition-tests/scenarios/` — feature_story, bug_fix, security_story YAMLs
- `skills/testing/composition-tests/test_composition.py` — 29 tests across 9 test classes:
  - CannedPipelineTest (3): full pipeline, abbreviated pipeline, security story
  - HandoffChainTest (4): artifact refs, claims, triple reject escalation, security reject
  - AuthorityPreservationTest (4): FACT/VERIFIED agent blocks, SYSTEM FACT, classification isolation
  - FailureCascadeTest (5): iteration cap, escalation, stale snapshot, merge bypass, replan
  - RiskTierConsistencyTest (3): monotonicity, human override, tier floor
  - LifecycleCompositionTest (4): full lifecycle, worktree isolation, dependency order, timing
  - InformationFidelityTest (3): change-set linkage, bad-ref rejection, hash chain integrity
  - LiveModeGuardTest (1): env var opt-in required
  - StageGraphConsistencyTest (2): scenario stages in graph, valid agent roles

### F.7 Remaining Work

- **Migration scenario** and **spike scenario** YAMLs (2 more of the planned 5)
- **Scaling scenario** with synthetic 50-story epic (F.4)
- **Live mode runner** — the framework is ready; implementation needs LLM API wiring
- Wire into CI as a nightly or weekly job

---

## Cross-references

- Layer A (Skill Output Evals): `skills/testing/eval-harness/`
- Layer B (Handoff Contracts): `skills/testing/pipeline-tests/`
- Layer D (Adversarial ASI01/06/08): `skills/mcp-servers/adlc-mcp/tests/aat/`
- Layer E (Property Invariants): `skills/testing/invariant-tests/`
- Layer F (Composition): `skills/testing/composition-tests/`
- Enforcement map: `docs/enforcement-map.md`
- Existing AAT: `skills/mcp-servers/adlc-mcp/tests/aat/test_asi02_tool_misuse.py`, `test_asi03_authorization.py`
