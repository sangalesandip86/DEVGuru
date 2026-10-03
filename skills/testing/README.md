# /testing

Progressive skill group (plan §3, §4.8). Skills here are routed in by
[`skill-routing`](../skill-routing/) and risk-tiering as real tasks need them; only
`security-testing` and `ai-agent-testing` are required before the platform runs with real
autonomy (plan §9 step 10).

| Sub-group | Skills | Phase |
|---|---|---|
| `test-architecture` | test-strategy, test-pyramid-advisor, **test-repo-discovery** (v3.1) | progressive (discovery: 1) |
| `test-design` (v3.1) | **test-case-design**, **bdd-feature-authoring**: qa-derive, code-blind | 1 |
| `test-data` (v3.1) | **test-data-synthesis** | 1 |
| `test-implementation` (v3.1) | **suite-authoring**, **bdd-step-binding**: test-engineer | 1 |
| `web-ui-automation` | playwright-expert, selenium-expert, visual-regression, headless-vs-headed | progressive |
| `mobile-automation` | appium-expert, ios-xcuitest, android-espresso, device-matrix, **flutter-testing**, **detox-react-native** (v3.1) | progressive |
| `api-contract-testing` | pact-consumer-driven, postman-newman, schema-validation | progressive |
| `test-maintenance` | flaky-test-intelligence, test-data-management, self-healing-locators | progressive |
| `performance-testing` | load-testing-expert, perf-baseline-tracker, bottleneck-analysis | progressive |
| `security-testing` | sast-scanner, sca-dependency-audit, secret-scanning, deployment-verification | 1 |
| `ai-agent-testing` | prompt-injection-tests, tool-misuse-tests, agent-authorization-tests, policy-bypass-tests | 1 |

## Authority rule shared by every testing skill

- A test, scan, or check **passing in CI** is machine evidence. The server ingests it and
  sets `VERIFIED`. No agent writes `VERIFIED` (plan §5.5).
- An agent's judgment about tests — strategy, coverage adequacy, flake diagnosis, triage of
  a scanner finding — is `REVIEWED`, with evidence attached.
- Results produced by running a command are recorded as `FACT` by the PostToolUse
  fact-writer hooks, not by the model.

## Oracle versus binding (plan §4.13, ADR 0003)

```
READY story ─► qa-derive (code-blind) ─► plans/test-designs/ST-n.yaml or *.feature   (frozen at ac_hash)
                  test-case-design · bdd-feature-authoring · reads step-patterns.json only
                                    ▼
               test-engineer (reads code; writes test assets only)
                  test-repo-discovery → suite-authoring (mode A/B/C, impact plan) → test-data-synthesis
                  → bdd-step-binding / stack skills (playwright-expert, flutter-testing, detox-react-native, …)
                                    ▼
               CI (SYSTEM): integrity guard · red/green · flake gate · mutation · PII scan · no-sleep · dry-run
```

- **The oracle comes from the AC and contracts; the binding comes from the code.** A value found in the code that
  contradicts the spec is a QUESTION or a defect, never a test expectation.
- **An expectation changes only when the AC changes.** CI enforces this with
  [`test_integrity_guard.py`](../enforcement/ci-checks/test-integrity/test_integrity_guard.py).
- **Characterization mode** (ADR 0004 §3) exists for legacy code with no AC. Those tests are tagged
  `characterization` and never count as AC verification.
- **Every skill starts with a Preflight** ([stage-preflight](../workflow/stage-preflight/SKILL.md),
  [workspace-resolver](../workflow/workspace-resolver/SKILL.md)). A missing framework becomes Mode C, as its own
  `TEST_AUTOMATION` story.
- **Enforcement artifacts** live in [`../enforcement/ci-checks/test-integrity/`](../enforcement/ci-checks/test-integrity/README.md).
