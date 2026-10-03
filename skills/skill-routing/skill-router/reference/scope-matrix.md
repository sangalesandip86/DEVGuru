# Scope Matrix

<!-- reconstructed: v2 source not provided; review -->

Two kinds of binding: **mandatory** (policy-loaded, cannot be skipped or removed) and
**contextual** (added when analysis shows they are relevant). Paths are relative to `skills/`.

## Always mandatory (every session)

| Skill | Phase available |
|---|---|
| `grounding/evidence-gate` | 0 |
| `grounding/ambiguity-escalation` | 0 |
| `grounding/trust-boundaries` | 0 |
| `grounding/agent-failure-modes` | 0 |
| `grounding/human-review-format` | 0 |
| `core/evidence-ledger` | 0 |
| `core/fact-classification` | 0 |
| `governance/default-permissions` | 0 |
| `self-improvement/failure-capture` | 1 |

## Mandatory by trigger

| Trigger (Phase 1 keyword/path; Phase 2 domain) | Mandatory skills / roles | Minimum tier |
|---|---|---|
| Any control-file path (`governance/default-permissions/reference/control-file-paths.json`) | `grounding/trust-boundaries` (control-files), `governance/default-permissions`, human approval | CRITICAL |
| `payment`, `billing`, `invoice`, `fee`, `refund`, `ledger`; paths `payment/`, `billing/` | `testing/security-testing/*`, roles `security-reviewer`, `architect` | HIGH |
| `auth`, `login`, `token`, `session`, `permission`, `rbac`, `oauth`, `password`; paths `auth/`, `security/` | `testing/security-testing/sast-scanner`, `testing/security-testing/secret-scanning`, role `security-reviewer` | HIGH |
| `migration`, `schema`; paths `*/migrations/*`, `*.sql` | `change-management/risk-tiering`, `change-management/snapshot`, role `architect` | HIGH |
| Public API change: `openapi`, `proto`, `graphql`, route files, `*.avsc` | `contracts/compatibility-check`, `testing/api-contract-testing/*`, role `architect` | HIGH |
| Dependency manifest / lockfile changed | `testing/security-testing/sca-dependency-audit` | MEDIUM |
| More than one repository in scope | `change-management/change-set`, `change-management/dependency-discovery` | MEDIUM |
| Concurrent tasks in one Change Set | `change-management/parallel-execution` | MEDIUM |
| Agent / prompt / LLM code (`prompt`, `llm`, `agent`) | `testing/ai-agent-testing/*` | HIGH |
| Any code change | roles `code-reviewer`, `qa-derive`, `qa-diagnose` | MEDIUM |
| Docs-only change | none beyond always-mandatory | LOW |

Missing roles/skills for the current build phase resolve through Degraded Mode (§2): route to a named human.

## Mandatory by product-planning work (v3.1 §4.12)

| Trigger | Mandatory skills / roles |
|---|---|
| Any new requirement, or any story create/edit/split work | `product-planning/requirement-intake`, `product-planning/story-writer`, `product-planning/definition-of-ready` |
| Story refinement requested, or a story is in `REFINING` | `product-planning/story-refinement` (three-amigos: product-planner, qa-derive, developer) |
| Developer task start | `product-planning/definition-of-ready` check: the linked story (`Implements: ST-n` / `story_refs[]`) must be `READY`; if not, stop and raise a `QUESTION` |
| Change Set reaching `VERIFYING` with linked stories | `product-planning/definition-of-done` |
| Epic decomposition (Phase 2) | `product-planning/epic-decomposer` |
| Milestone / release planning (Phase 2) | `product-planning/milestone-planner` |

## Mandatory by story type (`product-planning/policies/story-types.yaml`)

The type floor also feeds the effective tier = max(type floor, path tier, computed tier)
(`change-management/risk-tiering`).

| Story type | Mandatory skills / roles | Tier floor |
|---|---|---|
| `API_CONTRACT` | `contracts/contract-registry`, `contracts/compatibility-check`, `testing/api-contract-testing/*`, role `architect` | HIGH |
| `DATA_MIGRATION` | `change-management/snapshot`, rollback plan + rollback test `VERIFIED` (story DoR/DoD, `product-planning/policies/dod-policy.yaml`), role `architect` | HIGH |
| `SECURITY_STORY` | `testing/security-testing/*`, role `security-reviewer` | HIGH |
| `UI_STORY` | `testing/web-ui-automation/playwright-expert`, `testing/web-ui-automation/visual-regression` | — |
| `INFRASTRUCTURE` | `change-management/snapshot` (IaC always-overlap), `testing/security-testing/deployment-verification` | MEDIUM |
| `DOCUMENTATION` | none beyond always-mandatory | LOW |

A declared type that the diff contradicts (e.g. `DOCUMENTATION` touching code) is a scope violation;
the bindings and tier of the actual diff apply.

## Mandatory by test-engineering work (v3.1 §4.13)

| Trigger | Mandatory skills | Role |
|---|---|---|
| Any task that creates or updates tests | `testing/test-architecture/test-repo-discovery`, `testing/test-implementation/suite-authoring` | test-engineer |
| Any test-design task | `testing/test-design/test-case-design` | qa-derive |
| Cucumber/BDD runner detected in the repo (`stack_fingerprint.py`) | `testing/test-design/bdd-feature-authoring` (qa-derive); `testing/test-implementation/bdd-step-binding` (test-engineer) | qa-derive, test-engineer |
| Any fixture, builder, seed, or test-data change | `testing/test-data/test-data-synthesis` | test-engineer |

## Stack-driven bindings (Phase 2 routing, v3.1 §4.13)

Phase 2 reads the `stack_fingerprint.py` output — a `FACT` entry written by the discovery hook and
cached per `snapshot_id` — and binds the stack skills for every runner and UI paradigm it reports.
Routing does not infer the stack by reading files itself. **Over-include on doubt:** if the
fingerprint is missing, stale, or ambiguous (several runners, partial detection), bind every
plausible stack skill rather than guess one, and re-run discovery.

| Fingerprint reports | Bind |
|---|---|
| Playwright | `testing/web-ui-automation/playwright-expert` |
| Selenium / WebDriver | `testing/web-ui-automation/selenium-expert` |
| Visual snapshot tooling, or `UI_STORY` | `testing/web-ui-automation/visual-regression` |
| Flutter (`flutter_test`, `integration_test`, patrol) | `testing/mobile-automation/flutter-testing` |
| React Native + Detox | `testing/mobile-automation/detox-react-native` |
| Appium | `testing/mobile-automation/appium-expert` |
| XCUITest | `testing/mobile-automation/ios-xcuitest` |
| Espresso | `testing/mobile-automation/android-espresso` |
| Pact | `testing/api-contract-testing/pact-consumer-driven` |
| Postman / Newman | `testing/api-contract-testing/postman-newman` |
| k6 / JMeter | `testing/performance-testing/load-testing-expert` |
| Cucumber / Gherkin | BDD bindings above |
| No framework for the needed test tier | No stack skill. Greenfield framework setup is its own `TEST_AUTOMATION`/`INFRASTRUCTURE` story (framework choice is a `DECISION` + ADR) and is never done inside a feature story |

## Contextual (advisory) by analysis

| Signal | Skills |
|---|---|
| Web UI files changed | `testing/web-ui-automation/playwright-expert`, `testing/web-ui-automation/visual-regression` |
| Mobile project detected | `testing/mobile-automation/*` |
| Flaky test history in repo | `testing/test-maintenance/flaky-test-intelligence` |
| Performance-sensitive path or SLO mention | `testing/performance-testing/*`, `engineering-design/scale-readiness-reviewer` |
| New service / data store / queue | `engineering-design/system-architect`, `engineering-design/data-store-selector`, `engineering-design/messaging-selector` |
| Design-quality review requested | `engineering-design/code-design-reviewer` |
| RAG / LLM integration work | `ai-integration/*` |
| Test strategy undefined | `testing/test-architecture/*` |

## Rules
- Over-include on doubt; excess loading is cheaper than a missed binding.
- A trigger matched in either phase is mandatory for the rest of the task.
- Repeated Phase 2 near-misses for one domain are the signal to add keywords here — via the
  self-improvement `REVIEWED` → `APPROVED` pipeline, since this file is platform configuration.
