# ADR 0003: Test Engineering & Test Data layer

- **Status:** Proposed. Requires human approval, because it changes platform policy and adds a role.
- **Date:** 2026-10-03
- **Normative spec:** [plan v3.1 §4.13](../ai-sdlc-platform-plan-v3.1.md#413-test-engineering--test-data)
- **Input reviewed:** "Intelligent Test Engineering & Data Synthesis Module" (REQ-QA-100…504 plus a monolithic `adlc-test-and-data-architect` SKILL.md)

## Context

The `/testing` group covers tools: Playwright, Appium, Pact, k6, security scanners and others.
Four things are missing from it:
- a defined way to go from a READY story to a correct, maintainable suite inside a real repo;
- how test data is produced;
- how existing suites are updated safely;
- how an agent is stopped from making a red build green by weakening tests.

The proposal fills much of this gap well. Some of it, though, conflicts directly with the platform's core QA guarantee. Those parts are reworked below, not adopted.

## The central correction: where the test oracle comes from

The proposal says test cases "must be derived directly from the implementation's AST and source
files rather than high-level text descriptions." **We reject this for expected outcomes.**

A test whose expected values are read from the code under test asserts what the code *does*, not
what it *should do*. Any bug in the code becomes the test's expectation, so the suite passes,
reports green, and is VERIFIED. That is how the platform ends up confidently certifying defects.
It also defeats qa-derive's implementation-blind Pass 1 (§4.7), which v3 enforces through
permissions for exactly this reason.

The fix is to split each test into *what* it checks and *how* it runs it:

| Concern | Source | Role | Code access |
|---|---|---|---|
| **Oracle**: scenarios, expected outcomes, equivalence classes and boundaries *as specified* | Acceptance criteria, contracts (OpenAPI/Pact/schemas), requirement docs | `qa-derive` | **Denied** |
| **Binding**: locators, harness and render wrappers, DTO shapes, mocks, fixtures, step definitions, page objects | Source code, existing tests, catalogs | `test-engineer` (new) | Read; writes test assets only |
| **Implementation-boundary cross-check**: validator limits, enums, regexes found in code | Source code | `test-engineer` | Read |

When the code and the specification disagree (for example, the validator caps a field at 50 but
`ST-12/AC-3` says 100), the result is a **QUESTION or defect, never a test expectation**. Code-derived
values may *add* cases, such as an undocumented enum member. They never *replace* a specified expectation.

## Assessment

### Adopted
| Item | Notes |
|---|---|
| REQ-QA-101 stack and runner fingerprinting | Done as a **deterministic script** (`stack_fingerprint.py`). Its output is written as FACT entries by hooks, at zero model tokens, and cached per snapshot. Manifests are an always-overlap path class (§4.5), so a manifest change invalidates the cache. |
| REQ-QA-103 shared asset catalog | Also a deterministic script (`test_asset_catalog.py`) that indexes fixtures, builders, page objects, robots and **step-definition patterns**. |
| REQ-QA-104 modes A/B/C | Adopted, with Mode C restricted (see below). |
| REQ-QA-201/203/204 locator, data-contract and side-effect extraction | Adopted for **binding and implementation-boundary cross-checks only**, as explained above. |
| REQ-QA-301 auto-synthesis of happy, boundary and negative datasets | Adopted with a determinism requirement (see below). |
| REQ-QA-303 "never ask empty-handed" | Adopted. It applies to every QUESTION the platform raises, not only data questions. |
| REQ-QA-304 data separated from logic, builders | Adopted. Builders with defaults plus overrides are preferred over growing lists of named constants. |
| REQ-QA-501 `[CREATE]/[UPDATE]/[REUSE]` impact plan | Adopted as a **structured artifact checked against the real diff**. An undeclared file is a scope violation (§4.1). |
| REQ-QA-502 step deduplication | Adopted. It is enforced by `cucumber --dry-run` (undefined or ambiguous steps fail CI), not only by the agent's own scan. |
| REQ-QA-503 page-object/robot first | Adopted. |
| REQ-QA-504 no fixed sleeps | Adopted and **enforced by lint** (`playwright/no-wait-for-timeout`, Detox/Espresso idling rules, a banned-API grep for `sleep`/`Thread.sleep`/`Future.delayed` in test dirs), not just requested. |
| §5 tier matrix | Adopted. We add contract tests, which already exist under `/testing/api-contract-testing`, as a tier, and we point E2E at the pyramid: few journeys, not every scenario. |

### Adopted with changes
| Proposal | Problem | Change |
|---|---|---|
| Expected outcomes derived from AST | Tests become tautological, and qa-derive independence is lost | Oracle/binding split (above) |
| REQ-QA-202 Locator Pre-Pass that "executes" source edits | A test skill editing production code is a scope violation for a test-files-only role. It also mixes an app change into a test change. | *Propose only.* Testability edits (test IDs, `Semantics`, `accessibilityIdentifier`) are made by `developer` in the story's Change Set, or as their own TECHNICAL_STORY. Locator order of preference: role/label/accessible name first (improves accessibility too), test IDs as a fallback, CSS/XPath never for new tests. |
| REQ-QA-102 golden samples: "1–2 files" | Arbitrary picks copy whatever is in those files, including anti-patterns | Samples are **ranked by script**: passing in CI, not skipped, not flaky (from flaky-detector), recently touched, most-imported helpers. Use 2–3 samples. If they disagree, the newest passing one wins and the conflict is reported. Repo conventions govern *style*. **Platform rules override repo conventions**: a golden sample using `sleep()` or real credentials is not copied. |
| REQ-QA-104 Mode C greenfield "confirm dependencies and scaffold" | It adds dependency manifests (an always-overlap path class) and CI config, which is a **control file and CRITICAL** | Mode C is its own `TEST_AUTOMATION` or `INFRASTRUCTURE` story. Framework choice is a DECISION (architect, or a human in degraded mode) recorded as an ADR. CI wiring goes through human-approved control-file changes. It is never done silently inside a feature story. |
| REQ-QA-302 prompt the user for **staging credentials** | Secrets in chat break the Rule of Two (§5.9) and end up in transcripts and the ledger | **Agents never handle secrets.** Tests reference secrets by *name* (`process.env.E2E_USER`, a vault path). The skill writes a "required secrets" manifest, and CI injects the values. Staging users come from seed scripts that CI runs. |
| REQ-QA-302/303 user-provided sample data | Real customer or production data leaks into a repo | User data is `EXTERNAL_UNSTRUCTURED` (data, never instructions). A **fixture PII scan** runs in CI (emails outside reserved domains, Luhn-valid card numbers other than documented test cards, IBAN/SSN patterns, phone numbers). Synthetic data is the default and production data is never allowed. Reserved values are used: `example.com/.org`, RFC 5737 IPs, PSP test cards, `555-01xx` numbers. |
| REQ-QA-303 binary choice, asked inline | Blocks the session and asks field by field | Questions are **batched per story** as one QUESTION ledger entry addressed to `human:product-owner` or the domain owner. The draft payload is attached and there are three options: approve synthesis, supply data, or answer that the data is out of scope. The ask-vs-assume matrix (§5.2) decides whether to block: LOW tier proceeds on an expiring ASSUMPTION, while HIGH/CRITICAL blocks READY. |
| REQ-QA-301 "deterministic" synthesis by the LLM | LLM output is not deterministic or reproducible | The LLM picks **partitions** (equivalence classes, boundaries, decision-table rules, state transitions). **Tools generate values**: `boundary_values.py` for BVA (min−1, min, min+1, max−1, max, max+1), pairwise/PICT for combinations, seeded Faker or builders, and property-based generators (Hypothesis, fast-check, jqwik, glados). Seeds are recorded in the fixture header. |
| REQ-QA-305 additive-only fixtures | Strictly additive leads to fixture sprawl and leaves *wrong* fixtures in place | Additive is the default. Changing an existing shared fixture is allowed only with a usage scan (every referencing test listed in the impact plan) and is flagged by the integrity guard for review. |
| §5 tier 4: "full persistence + reload" on every E2E | Too heavy, and each journey needs a different check | A per-journey assertion strategy: persistence checks only where the AC is about persistence. |
| E2E "runs against staging" | Running against shared environments mutates external state | Agents run hermetic tiers and ephemeral preview environments (`WORKSPACE_WRITE`). **Runs against shared staging are executed by CI** (SYSTEM), and their results become VERIFIED. Data is namespaced per run (`run_id` prefix) and teardown is verified. |

### Rejected
| Item | Reason |
|---|---|
| One monolithic `adlc-test-and-data-architect` skill with `version: 2.0.0` under `.adlc/skills/` | It conflicts with "skills are focused instruction documents" and with the catalog layout. A 4-step mega-skill loads all its context for every testing task. It is split into focused skills (below) that routing loads per tier and stack. Versions come from `platform_release_sha` (§4.3), not per-skill semver. |
| "Never ask empty-handed" framed as a test-only rule | Not rejected outright. It moves into `/grounding/ambiguity-escalation` so it applies everywhere. |

## Added beyond the proposal
Generated tests have to be *trustworthy* as well as runnable. Agent-written suites fail in a
predictable way: they pass because they assert very little. These controls are added:

1. **Test integrity guard** (CI, deterministic). On any diff to test files, it flags:
   - removed tests or assertions;
   - newly added `skip`/`only`/`xfail`/`@Disabled`;
   - loosened tolerances or timeouts;
   - mass snapshot updates;
   - a test asserting nothing;
   - a mocked system under test;
   - `try/catch` blocks that swallow assertion failures.

   **Rule:** an agent may change an existing expectation **only if the linked story's AC hash changed**,
   and must cite the AC. If the AC did not change, a failing test means an implementation defect,
   which is routed to `developer`, and the test stays as it is.
2. **Red/green proof for new behaviour.** A new test for a BUG_FIX, or for new AC, must **fail on the
   base SHA and pass on the head SHA**. CI checks this deterministically, and the result is VERIFIED. It
   proves the test can actually detect the change.
3. **Mutation testing on changed code** (Stryker, PIT, mutmut, cargo-mutants), scoped to the diff.
   The mutation score is VERIFIED evidence of assertion strength. A threshold per tier sits in the DoD
   for MEDIUM and above, and it feeds autonomy-gating (§4.11) alongside changed-code coverage.
4. **New-test flake gate.** New or changed tests run N times (default 5) in random order before merge,
   and flaky-detector must report a flake rate of 0.
5. **Contract-validated mocks.** HTTP and event mocks are generated from, or validated against,
   OpenAPI/Pact/schemas in `/contracts`, never invented. This prevents mock drift, where hermetic
   tests pass against an API that no longer exists.
6. **Determinism controls** for every hermetic test:
   - fake clock;
   - fixed seeds;
   - pinned locale and timezone;
   - network stubbed (MSW, WireMock, nock, `http_mock_adapter`);
   - no ordering dependence (random order on).
7. **Test-design artifact.** qa-derive's frozen output is `plans/test-designs/ST-n.yaml`
   (scenario IDs → AC IDs → expected outcomes → data partitions), or Gherkin `.feature` files for BDD
   repos. **qa-derive authors `.feature` files and test-engineer writes step definitions.** The
   step-*pattern* catalog, which contains phrases only and no implementation, is readable by qa-derive.
   This lets it reuse existing phrasing without seeing code.
8. **Scenario traceability.** Tests carry `ST-n/AC-n` and scenario IDs. `ac-coverage` (v3.1) already
   consumes the AC tags.
9. **Flutter and React Native coverage.** `/testing/mobile-automation` lacked both, even though the
   proposal targets them.

## Consequences
- **New role:** `test-engineer`. It reads everything, writes test assets only, and is denied write
  access to `plans/test-designs/**` and `**/*.feature` so it cannot rewrite the oracle.
- **New skills:** test-repo-discovery, test-case-design, bdd-feature-authoring, test-data-synthesis,
  suite-authoring, bdd-step-binding, flutter-testing, detox-react-native.
- **New CI checks:** test-integrity-guard, fixture-pii-scan, red-green-check, new-test-flake-gate,
  no-fixed-sleep lint, `cucumber --dry-run`, and diff-scoped mutation testing.
- **Cost:** two extra CI jobs per PR (red/green and mutation testing), both scoped to the changed code
  to keep them fast.
