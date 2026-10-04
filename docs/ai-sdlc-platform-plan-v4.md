# AI SDLC Platform — Consolidated Build Plan v4

> **v4 changes (from v3.1):** v3.1 was a design document written before the code. v4 is written **from the code that exists in this folder on 2026-10-03** and from the full review in [`review/2026-10-03-platform-review.md`](review/2026-10-03-platform-review.md). Three kinds of change:
> - **As-built, not as-planned.** Section 3 is the real tree (83 skills, 108 scripts, one MCP server with 4 modules, 10 roles, 6 ADRs). Section 4 records what each group *actually does today*, with its enforcement status in three honest categories: **Enforced** (artifact + test exercises the block), **Detects** (reports, does not block), **Guideline** (prose only). v3.1's "enforced by" claims that were not true are downgraded here.
> - **Remediations folded in as plan items** (§9), each with the reasoning for why that fix was chosen over its alternatives: shared `repo-facts` engine (one AC hash, one path-tier table, one manifest parser); SYSTEM write path for the ledger so `VERIFIED` is reachable; per-workspace ledger with required scope on every write; redaction in the fact-writer; `.adlc/**` outputs hash-anchored in the ledger; red/green, flake and mutation gates shipped as scripts; Copilot limits stated and routed around; MCP 2026-07-28 alignment; signed platform releases; AI-authorship trailers; metrics exporter.
> - **Why each design is kept.** Every principle in §1 and every cross-cutting rule in §5 now carries a one-line *why this and not the alternative*, because a plan that only says *what* gets re-litigated every quarter.
>
> Everything in v3.1 that is not contradicted here still holds; v3.1 remains the normative text for §4.12–§4.15 specifications and is linked rather than copied. v3 is kept for history.

> How to use this document: §1 tells you what the platform refuses to compromise on and why. §2 is the phase order (unchanged) with the real status of each. §3 is the real folder tree — your map. §4 says, per group, what is built, what it enforces, and what is still missing. §5 is the shared logic every skill references. §6 is the MCP server as it exists plus the agreed routing/concurrency design. §7 is measurement. §8 is tool compatibility as of the 2026-10 vendor docs. §9 is the build sequence with status and the remediation order.

---

## Table of Contents

1. [Overview & Core Principles — with reasoning](#1-overview--core-principles--with-reasoning)
2. [Build Phases — status](#2-build-phases--status)
3. [Folder Tree — as built](#3-folder-tree--as-built)
4. [Skill Groups — as built, enforcement status, gaps](#4-skill-groups--as-built-enforcement-status-gaps)
5. [Cross-Cutting Design Rules — with reasoning](#5-cross-cutting-design-rules--with-reasoning)
6. [MCP Server — as built and target](#6-mcp-server--as-built-and-target)
7. [Pilot & Measurement](#7-pilot--measurement)
8. [Tool Compatibility — Claude Code / GitHub Copilot (2026-10)](#8-tool-compatibility--claude-code--github-copilot-2026-10)
9. [Build Sequence — status and remediation order](#9-build-sequence--status-and-remediation-order)
10. [Decision Log — what we rejected and why](#10-decision-log--what-we-rejected-and-why)

---

## 1. Overview & Core Principles — with reasoning

**What this is:** an AI-agent platform for the software development lifecycle, shipped as a catalog of **skills** (instruction documents), tool-neutral **roles** (generated into Claude Code subagents and Copilot custom agents), **enforcement hooks and CI checks**, and one **MCP server** (`adlc`) holding the stateful engines. It runs inside Claude Code and GitHub Copilot-class assistants. It is stack-agnostic by design: deterministic scripts fingerprint a repository and routing binds the stack skills that fit, so the same platform serves a Flutter app, a Spring service, a Go CLI or a TypeScript monorepo.

**Non-negotiable principles.** Each row: the rule, then *why this is the best choice* and what it beats.

| # | Principle | Why this, not the alternative |
|---|---|---|
| 1 | The **Change Set** (requirement + every repo/contract/environment it touches, pinned to a snapshot) is the unit of work. Single-repo: the forge issue + PR *is* the Change Set. | Repos are implementation boundaries; real changes cross them. A custom state machine for single-repo work (v2) duplicated what the forge already records — merge, review, deploy — and gave agents a second place to lie. Reusing forge state removes a forgery surface at zero build cost. |
| 2 | **"Latest" is never a reproducibility mechanism.** Every analysis, verification and ledger entry names a `snapshot_id` / `repo@sha`. | Any cached result keyed to "main" is stale the moment someone merges. Pinning makes staleness detectable (`validate_snapshot_currency`) instead of silent. |
| 3 | **Three authority levels.** `VERIFIED` only from machine-ingested evidence written by the server; `REVIEWED` is an agent judgment with evidence; `APPROVED` only by an authenticated human. An agent's role identity never implies human authority. | Two-level systems let "the agent checked" count as verification — the exact trust failure in the 2025–26 developer surveys (trust in AI output fell to 29%). CISA/NSA 2026: agents must not decide which of their own actions need sign-off. Three levels is the minimum that encodes both. |
| 4 | **No state transition by prompt text or self-report.** Only hooks, managed settings, server checks or observed forge events move state. | Prose can be injected; a server check cannot be paraphrased away. This is the structural half of the Rule of Two. |
| 5 | **Unknown → more scrutiny.** Unknown tier → HIGH; unknown compatibility → INCOMPATIBLE; unknown dependency → UNRESOLVED. | Every permissive default turns missing evidence into permission. Fail-closed makes "we didn't know" auditable rather than exploitable. |
| 6 | **Every claim in a structured artifact traces to a source**, or becomes a QUESTION or an expiring ASSUMPTION. This is enforced on handoffs/DECISIONs (schema), not on free prose (honestly a guideline). | Grounding free prose mechanically is impossible; grounding the artifacts gates read *is* possible and is where decisions are made. Claiming more would be the ASI09 trust exploitation the platform tests for. |
| 7 | **Untrusted input is data**, enforced structurally (Rule of Two: no session holds untrusted input + secrets/production data + external mutation). Keyword flags are supplementary. | Paraphrase defeats keywords in one step (tested as AAT-ASI06-008). Removing one of the three legs defeats the attack regardless of wording. |
| 8 | **Control files are never agent-writable** (hooks, skill/agent/MCP config, AGENTS.md, CLAUDE.md, CODEOWNERS, rulesets, CI, planning policies). Any write is CRITICAL + human approval, denied at managed-settings level. | Every 2025–26 agent incident of note is "agent rewrote its own config" (CurXecute, Comment-and-Control, 24k secrets in MCP configs). Only a deny the agent cannot edit stops it. |
| 9 | **Cost optimisation is subordinate to accuracy.** It decides what loads and which model runs, never whether grounding happens. | Gartner 2026: token spend will exceed salaries; the temptation to skip verification to save tokens is real and must be ruled out by policy, not left to judgment. |
| 10 | **Scale process to risk.** A README change and a payment migration do not pass the same gates. | Uniform heavy process is what makes teams route around the platform (the override-rate metric exists to catch this). |
| 11 | **Self-improvement only through human-gated review** of sanitized lessons with synthetic red/green reproductions. Never silent prompt rewriting. | Raw incidents leak customer data across projects; abstract notes cannot be run. Lesson + synthetic eval is the only form that is shareable *and* testable (ADR 0006). |
| 12 | **Skills inform; hooks and servers enforce.** A skill is an instruction document, never a callable module. Every enforcement claim names its artifact and its test. | The single biggest finding of the review was enforcement language without enforcement. Naming the test closes the gap and makes the claim checkable in CI. |
| 13 | **Mandatory skills are loaded by policy, not LLM judgment**, computed from stack facts + paths + story type, re-evaluated as understanding deepens. | Vendor guidance and routing research agree: LLM skill selection is advisory and degrades with catalog size. Computed bindings + `paths:` scoping are deterministic. |
| 14 | **No work reaches a Change Set without a READY story.** Plans are code; READY/DONE derived by gates; AC frozen at READY. Exception: LOW-tier BUG_FIX/DOCUMENTATION inline story, still gate-checked. | ISO 29148 traceability and the oracle rule both need a frozen, ID'd contract. Derived status means the status *is* the evidence; a tracker card is not. |
| 15 | **Expected test outcomes come from AC and contracts, never from code.** Oracle (qa-derive, code-blind) is separate from binding (test-engineer). An expectation changes only when the AC changes. | 100% coverage / 4% mutation score is the documented LLM failure; agents "fix" red builds by editing expectations. Blinding the oracle is the only structural defence. |
| 16 | **Brownfield work follows the project's own standards** (platform rules > declared standards > observed conventions > generic guidance). Deviations are DECISIONs with ADRs. | AI PRs are +51% larger with +441% review time (Faros 2026); most of it is style drift and silent architecture change. Consistency-over-preference is the cheapest route to reviewable diffs. |
| 17 | **Any stage to any stage, never skipping a gate.** Preflight classifies inputs SATISFIED / ADOPT / BACKFILL / ASK / BLOCK. | Users arrive with documents, backlogs or code. Starting late must skip *work already evidenced*, never *gates*; otherwise "start at IMPLEMENT" is a DoR bypass. |
| 18 | **Stack-agnostic by deterministic discovery.** Fingerprint, catalogue, conventions and workspace facts come from stdlib scripts, cached per snapshot, recorded as FACT; the LLM reads them, never re-derives them. | Reproducible, zero-token, cacheable, and the way Linguist/Renovate/Nx already work. An LLM skimming files guesses differently each run. |
| 19 | **Agents will fail.** Iteration caps (vendor `maxTurns` + orchestrator counter), failure-class retry policy, scope checks, resumable checkpoints. | Designing only the happy path produces the 59-minute-timeout-then-nothing failure Copilot's cloud agent already exhibits. |

---

## 2. Build Phases — status

Phases describe the order the **platform** is built. *Stages* (§4.14) describe a piece of **work's** path. Status as of 2026-10-03.

| Phase | Delivers | Status |
|---|---|---|
| **0** — Evidence ledger, grounding, enforcement, path-based tiers, default permissions | `core/`, `grounding/`, `enforcement/`, `governance/default-permissions/`, `adlc-mcp` evidence_ledger module | **Built, pre-pilot.** Gaps: no SYSTEM write path (VERIFIED unreachable); fact-writer stores raw content; `skills/**`/`dist/**` denies overreach in target repos; Bash bypass of path denies. |
| **1** — Planning core, routing, forge-native Change Sets, first roles (incl. product-planner, test-engineer), test-engineering core, self-improvement, security + AI-agent testing | `product-planning/`, `planning-gates/`, `skill-routing/`, `testing/{test-design,test-implementation,test-data}/`, `test-integrity/`, roles, `self-improvement/`, `testing/{security,ai-agent}-testing/` | **Mostly built, not integrated.** Gaps: AC hash diverges between gates and MCP; evidence exporter / status recorder / tracker projection missing; red/green, flake gate, mutation are prose; router is a document, not a script; no harness runs the AI-agent-testing catalogs. |
| **2** — Multi-repo / parallel Change Sets; full planning | `change-management/`, `change_management` + `work_planning` modules, epic/milestone/dependency skills | **Scaffolded.** Lifecycle table implemented and tested; approvals not epoch-scoped; two path-tier engines; no worktree orchestrator. |
| **3** — Contracts, remaining roles, governance | `contracts/`, `contract_registry` module, architect/product-owner/security-reviewer roles | **Scaffolded.** `check-can-i-deploy.py` is complete and fail-closed; drift detection is prose; no CI wiring. |

**Degraded Mode** (unchanged, keep): a required agent role that is not built routes to a **named human** (`stages.yaml → degraded_mode`), never a silent skip, never an indefinite block. *Why:* phased builds otherwise deadlock on their own prerequisites.

**Explicitly deferred (unchanged):** full semantic dependency graph; multi-dimensional risk scoring; cross-organisation lesson sharing; signed *third-party* skill supply chain; capacity planning / story points. *Why:* each needs observability data the pilot has not produced; building them first optimises for imagined load.

**Newly promoted from deferred to Phase 1/2 (v4):** signing of the *platform's own* releases (SLSA L2) — because the platform is a supply-chain input to every repo it touches; and a metrics exporter — because without a baseline the pilot cannot be judged.

---

## 3. Folder Tree — as built

Counts are files per directory as of 2026-10-03; `(+n)` are reference/scripts/tests under the skill.

```
docs/
  ai-sdlc-platform-plan-v3.md, -v3.1.md, -v4.md (this)      plan history
  authoring-conventions.md                                   SKILL.md format, vocabulary, integration contracts
  enforcement-map.md                                         rule → skill → enforcement point (to be made 3-column, §9 item 8)
  pilot-measurement.md · tool-compatibility.md
  adr/0001-mcp-modular-monolith … 0006-self-improvement-lessons
  review/2026-10-03-platform-review.md
  tools/check_skill_contracts.py                             83/83 skills carry stage/inputs/outputs/repo_roles + Preflight

skills/
  grounding/            5 skills  evidence-gate · ambiguity-escalation (ask-vs-assume, fail-safe defaults) · trust-boundaries (control-files, trust levels) · agent-failure-modes (failure-catalog) · human-review-format
  core/                 2 skills  evidence-ledger (identity-and-auth, ledger-entry-schema) · fact-classification · schemas/ledger-entry.schema.json
  self-improvement/     2 skills  failure-capture (+6 refs: failure-taxonomy, failure-class-map.json, incident schema, production-feedback …) · improvement-review (+5 refs: lesson schema, eval-case-conversion, pattern-threshold, lesson_lint.py, sanitize_check.py, build_blocklist.py)
  governance/           4 skills  default-permissions (control-file-paths.json, role-tool-permissions.md, control-file-policy.md) · autonomy-gating (verification-strength.md) · permission-scoping · policy-drift-check
  enforcement/          NOT skills
    lib/adlc_enforcement.py                                  normalises Claude/Copilot hook stdin
    hooks/control-file-guard · config-change-logger · fact-writer-hooks · registration/{claude,copilot}-hooks.json
    managed-settings/generate_deny_list.py · templates/{claude-code-managed-settings.json, copilot-org-controls.md}
    ci-checks/control-file-policy-check (5) · dependency-decision-check (2) · planning-gates (plan_lint, readiness_gate, completion_gate, ac_coverage, planning_lib, minyaml, ac_hash + tests) · test-integrity (test_integrity_guard, fixture_pii_scan, no_fixed_sleep_check, red_green_check.md*, new_test_flake_gate.md*, workflow.example.yml + tests)
    tests/ (40 tests)
  mcp-servers/adlc-mcp/                                      one server "adlc"
    src/adlc_mcp/{app.py, __main__.py (stdio)}
    kernel/ (identity, config, db, vocab, errors, mcp_compat, …)
    modules/evidence_ledger · change_management · contract_registry · work_planning   each: api.py domain.py store.py tools.py migrations/
    scripts/ledger_cli.py (append-fact | verify | purge | query) · adlc_credentials.py
    tests/ (82 tests incl. test_module_boundaries.py)
    reference/mcp-server-design.md
  skill-routing/        3 skills  skill-router (scope-matrix, two-phase-routing) · binding-vs-advisory (policy-precedence) · token-budget-optimizer (+6 refs)
  change-management/    5 skills  change-set (+7 refs incl. changeset.schema.json) · snapshot (staleness-policy) · dependency-discovery (scan-imports.py, scan-api-calls.py + tests) · risk-tiering (path-tiers.json, path_tier_lookup.py + tests, 3 refs) · parallel-execution
  contracts/            3 skills  contract-registry (contract-schema) · compatibility-check (check-can-i-deploy.py + tests) · drift-detection
  product-planning/     8 skills  requirement-intake · story-writer (AC standard, story schema, story types) · story-refinement (protocol, sizing) · definition-of-ready (readiness-gate ref) · definition-of-done (completion-gate ref) · epic-decomposer (slicing patterns) · milestone-planner (prioritization) · dependency-mapper
                                  policies/{story-types,dor-policy,dod-policy}.yaml (CONTROL FILES) · schemas/{requirement,epic,story,milestone}.schema.json
  workflow/             6 skills  stages.yaml · adlc-conductor (request-grammar, run-examples, checkpoint-format) · requirements-ingestion (ingest_documents.py) · workspace-resolver (resolve_workspace.py) · stage-preflight (stage_preflight.py) · brownfield-adoption (import_tracker.py) · repo-bootstrap (create_repo_from_request.py) · lib/workflow_lib.py · schemas/
  engineering-design/   7 skills  project-conventions (convention_scan.py + tests, 4 refs) · architecture-package (document-set) · system-architect (decomposition, scaling, 12 templates) · code-design-reviewer (SOLID, anti-patterns, perf) · data-store-selector · messaging-selector · scale-readiness-reviewer
  ai-integration/       3 skills  llm-integration-architect · prompt-engineer (prompt-patterns, eval-harness) · rag-pipeline-expert
  testing/             35 skills
    test-architecture/  test-strategy · test-pyramid-advisor · test-repo-discovery (stack_fingerprint.py, test_asset_catalog.py, test_discovery.py; discovery-outputs ref)
    test-design/        test-case-design (techniques, test-design.schema.json) · bdd-feature-authoring (gherkin style)
    test-data/          test-data-synthesis (boundary_values.py + tests; data-resolution-protocol)
    test-implementation/ suite-authoring (determinism-controls, impact-plan.schema.json + example) · bdd-step-binding
    web-ui-automation/  playwright-expert (selectors, flaky patterns) · selenium-expert · visual-regression · headless-vs-headed
    mobile-automation/  appium-expert · ios-xcuitest · android-espresso · device-matrix · flutter-testing · detox-react-native
    api-contract-testing/ pact-consumer-driven · postman-newman · schema-validation
    test-maintenance/   flaky-test-intelligence (flaky-detector.py + tests) · self-healing-locators · test-data-management
    performance-testing/ load-testing-expert (k6, JMeter refs) · perf-baseline-tracker · bottleneck-analysis
    security-testing/   sast-scanner · sca-dependency-audit · secret-scanning · deployment-verification
    ai-agent-testing/   prompt-injection-tests · tool-misuse-tests · agent-authorization-tests · policy-bypass-tests · reference/asi-mapping.md
  roles/               10 roles   product-owner · product-planner · architect · developer · qa-derive · qa-diagnose · test-engineer · code-reviewer · security-reviewer (each role.yaml + ROLE.md) · reference/{handoff-schema(.md,.json), conflict-resolution, reviewer-diversity} · scripts/generate_agents.py · tests/
dist/                  GENERATED  claude/.claude/{agents/*.md ×9, commands/adlc.md, settings.roles.json} · copilot/.github/{agents/*.agent.md ×9, prompts/adlc.prompt.md}
templates/repo-bootstrap/                                   AGENTS.md, CLAUDE.md shim, CODEOWNERS, CI, plans/ skeleton for new repos
examples/plans/                                             worked example REQ-1/EPIC-1/MS-1/ST-1..4 + evidence fixture (hand-written — to be regenerated, §9 item 2)
```
`*` = Markdown stub where a script is claimed.

**Planned consolidation (v4, §9 item 20):** the 83 skills above collapse to **31** — one skill per capability or test surface, stack variants as `reference/` files keyed by `stack.json` with `paths:` scoping, always-on rules as `.claude/rules/adlc-*.md` + role `skills:` lists, config explainers as reference docs. Full target catalog and move manifest: review Appendix B. *Why:* the level-1 skill listing is budget-capped (~1% of context) and 83 descriptions overflow it, so skills under-trigger; overlapping stack skills make the model choose what `stack.json` already knows; 20 copies of the same Preflight paragraph drift. Nothing is deleted — content moves one disclosure level down.

**Planned additions (v4, §9):** `skills/core/repo-facts/` (shared engine: manifests, workspace walker, path tiers, AC hash, canonical JSON); `skills/skill-routing/skill-router/scripts/route.py`; `test-integrity/{red_green_check.py, flake_gate.py, mutation_adapters.json, impact_plan_check.py}`; `ledger_cli.py {export-planning-evidence, record-planning-status, ingest-ac-coverage, record-gate}`; `tools/tracker_projection.py`; `tools/metrics_export.py`; `governance/ai-inventory.md`; `.github/workflows/release.yml` (cosign + in-toto).

---

## 4. Skill Groups — as built, enforcement status, gaps

Status legend: **Enforced** = artifact exists and a test exercises the block · **Detects** = artifact reports, nothing blocks on it yet · **Guideline** = prose only. Specs for §4.12–§4.15 remain in v3.1; this section records reality and the v4 decision per group.

### 4.1 `/grounding` — binding, cross-cutting
**Built:** all five skills with references; preflight pattern ("never ask empty-handed", batched QUESTION with proposed default) is applied consistently across 83 skills.
**Enforcement:** evidence-gate on handoffs — *Guideline* today (`record_handoff` does not validate `source`/`input_references`); trust-level derivation — *Enforced* for `trust_level` (server-derived), *Detects* for `source_type` (caller-supplied, see §6); control-files — *Enforced* on Claude Code Edit/Write, *Guideline* on Copilot and via Bash.
**v4 decision:** keep all text; add schema validation in `record_handoff`/`record_evidence` (cheap, fields exist). *Why:* turns the most-cited rule into a structural one without changing a skill.

### 4.2 `/self-improvement` — binding, cross-cutting (ADR 0006)
**Built:** incident = signal + ledger pointers; 20 failure classes in `failure-class-map.json`; lesson schema; `lesson_lint.py`, `sanitize_check.py`, `build_blocklist.py`; MCP `record_incident`, `record_lesson`, `query_incidents`, `query_lessons`.
**Enforcement:** sanitization fail-closed — *Detects* (script exists, not wired to `record_lesson`); human approval before ORG scope — *Enforced* in MCP.
**Gaps:** incident/lesson JSON schemas ≠ MCP validation; no test that a glossary term is blocked.
**v4 decision:** keep the design verbatim (it is strictly better than "short notes only" — see ADR 0006 §Assessment). Unify schemas (one file, loaded by both); add glossary-blocking test. *Why:* the control is the sanitizer; an untested sanitizer is a hope.

### 4.3 `/core`
**Built:** evidence-ledger and fact-classification skills; `ledger-entry.schema.json`.
**Gaps:** schema drifted from `store.py`; `purge` leaves no marker row.
**v4 decision:** generate the schema from the store column map in a test; append a SYSTEM `PURGE` entry naming the purged range. *Why:* auditors ask what was deleted and when; a hash chain with silent gaps fails that question.

### 4.4 `/skill-routing`
**Built:** scope-matrix (keyword/path/story-type/stack bindings), two-phase routing, binding-vs-advisory precedence, token budget references.
**Enforcement:** "mandatory loaded by policy" — *Guideline* (no router script, no orchestrator).
**v4 decision:** add `route.py` (inputs: `stack.json`, changed paths, story type, tier → binding set JSON recorded as DECISION) and put `paths:` frontmatter on every stack skill so Claude Code scopes them natively. Keep over-include-on-doubt. *Why:* research shows LLM selection degrades with catalog size and is advisory by nature; `paths:` is the vendor's deterministic mechanism and costs nothing. Alternative — trusting descriptions — is what the platform already says not to do.

### 4.5 `/change-management`
**Built:** change-set schema + lifecycle + approval matrix + completion criteria + resumability + tasks/checkpoints; snapshot staleness policy with always-overlap classes (incl. test-runner configs, v3.1); `path_tier_lookup.py` (fail-safe, control-files → CRITICAL, diff cap); `scan-imports.py` / `scan-api-calls.py` (UNRESOLVED default); parallel-execution rules. MCP `change_management` module with transition table, forge-event ingestion, `_integration_blockers`.
**Enforcement:** agents cannot set PLAN_APPROVED/INTEGRATED/RELEASED — *Enforced* (tested); invalid transitions — *Enforced*; tier fail-safe — *Enforced* in script; 3-attempt cap — *Guideline* (admitted); worktree isolation — *Guideline*; `dependency-decision-check` — *Detects* (not wired).
**Gaps:** second path-tier table inside the MCP module; approvals not epoch-scoped; BLOCKED exits incomplete (PLAUSIBLE).
**v4 decision:** one tier table (`repo-facts`), `approval_epoch` on Change Sets, property-tests on the transition table, wire `dependency-decision-check` into the IMPLEMENT/REVIEW gate, use subagent `maxTurns` as the vendor-native attempt cap. *Why:* approval of plan N must not authorize plan N+1 (ITIL normal change); two tier engines guarantee disagreement; `maxTurns` is the only cap the runtime itself enforces.

### 4.6 `/contracts`
**Built:** contract schema with compatibility directions; `check-can-i-deploy.py` complete (both directions, retained event versions, INCOMPATIBLE by default) with tests; drift-detection classification scheme; MCP `register_contract`, `record_deployment`, `check_compatibility`, `detect_drift`.
**Enforcement:** fail-closed compatibility — *Enforced* in script; CI gate — *Guideline* (no workflow); drift job — *Guideline*.
**v4 decision:** keep; Phase 3 wiring unchanged. *Why:* nothing to fix in the logic; the gap is deployment, which belongs to the pilot that needs contracts.

### 4.7 `/roles`
**Built:** 10 roles (v3's 7 + product-planner, test-engineer; product-owner retained), `role.yaml` + `ROLE.md`, generator to both vendors, handoff schema (md + json), conflict-resolution (domain-scoped REJECT, human lifts), reviewer diversity.
**Enforcement:** qa-derive code-blind — *Enforced* on Claude Code for Read/Edit/Write via managed denies; *Guideline* on Copilot (prose) and against Bash (qa-derive has no Bash ✔, but ledger `query_evidence` leaks developer file-read FACTs); test-engineer write-deny on oracle paths — same split; handoff schema — *Guideline* (not validated server-side).
**v4 decision:** (1) blind/reviewer roles run only on Claude Code or in a sandboxed runner, stated in §8; (2) role denies generated into the *managed* template keyed by subagent, not into project `settings.roles.json`; (3) `maxTurns`, `disallowedTools`, `isolation: worktree` added to generated subagents; (4) `AGENT_ROLES` in the server generated from `roles/*/role.yaml`. *Why:* project settings are REPOSITORY trust and agent-writable; Copilot has no path-deny primitive — pretending otherwise is the ASI09 failure applied to our own docs.

### 4.8 `/testing` (incl. v3.1 §4.13 test engineering)
**Built:** 35 skills. Discovery scripts (`stack_fingerprint.py`, `test_asset_catalog.py` incl. phrases-only `step-patterns.json`), test-design schema with techniques (ISO 29119-4 aligned), `boundary_values.py` (unspecified ≠ invalid, seeded), suite-authoring modes A/B/C + impact-plan schema, determinism controls per stack, BDD binding, stack skills (Playwright, Selenium, Flutter, Detox, Appium, XCUITest, Espresso, Pact, Newman, k6/JMeter), security scanners, AI-agent-testing catalogs mapped to OWASP ASI01/02/03/06/08/09.
**Enforcement:** expectation change needs AC-hash change — *Detects* (`test_integrity_guard.py` logic exists and is tested; CI wiring is an example YAML; overrides read from `head/`); PII scan — *Enforced* as script; no fixed sleeps — *Enforced* as script; red/green — *Guideline* (Markdown); new-test flake gate — *Guideline* (Markdown); mutation — **absent**; impact-plan-vs-diff — *Guideline*; AI-agent-testing — *Guideline* (no harness).
**Gaps:** fingerprint tables ~10× smaller than Renovate/Dependabot; no monorepo per-package stack; 20+ skills carry copy-pasted preflight paragraphs.
**v4 decision:** ship `red_green_check.py`, `flake_gate.py`, `mutation_adapters.json` (Stryker/PIT/mutmut/cargo-mutants diff mode) and add `mutation` to DoD `tier_gates` at MEDIUM+; move overrides to ledger REVIEWED entries; `impact_plan_check.py`; widen fingerprint to Renovate parity + workspace walker (via `repo-facts`); shared preflight reference; minimal harness running ASI03/ASI02 catalogs in CI. *Why:* every 2026 source (Google, Meta, Thoughtworks Radar 34, three arXiv studies) says mutation score, not coverage, is the only reliable guard against tautological LLM tests — and four skills plus the enforcement map already promise it. A wrong fingerprint mis-routes every stack skill, so the detection tables are a routing correctness issue, not polish.

### 4.9 `/engineering-design` and 4.10 `/ai-integration`
**Built:** project-conventions with `convention_scan.py` (declared standards + sha256, toolchain commands, dependency inventory by concern, module map, ranked golden files, `mixed_conventions` notes); architecture-package with 12 templates (C4, MADR ADR, NFR→tactics, integration inventory, STRIDE threat model, risk register, service map feeding `adlc.workspace.yaml`); system-architect (numbers-first); code-design-reviewer (SOLID/anti-patterns/perf with "needs a number" discipline); data-store and messaging matrices; scale-readiness checklist; LLM/RAG/prompt skills with eval-first loop and 2026 model tiering.
**Enforcement:** project toolchain in CI — *Enforced* by the project, not us; manifest-diff-without-DECISION — *Detects*; conformance REVIEWED — *Guideline* by design (judgment).
**Gaps:** `convention_scan.find_toolchain` reads root-only; detects conformance tools by filename but does not parse rule bodies.
**v4 decision:** keep all; per-package toolchain via `repo-facts`; optionally parse dependency-cruiser/import-linter/depguard rule bodies into `conventions.json.boundaries` so the architect reads declared boundaries rather than re-deriving them. *Why:* the precedence ladder (ADR 0005) is correct and already in every relevant skill; the remaining gap is data fidelity.

### 4.11 `/governance`
**Built:** control-file list (categories), role-tool-permissions matrix, control-file policy, autonomy-gating thresholds, permission-scoping (Rule of Two mapping), policy-drift-check (prose).
**Gaps:** `skills/**`/`dist/**` globs overreach target repos; managed-settings keys unverified against the live schema; no deployed-vs-template check; no AI inventory/impact assessment; no release signing.
**v4 decision:** split control-file categories (`platform-repo` vs `target-repo`); pin and verify settings keys (`permissions.disableBypassPermissionsMode`, `allowManagedPermissionRulesOnly`, `allowManagedHooksOnly`, `allowManagedMcpServersOnly`+`allowedMcpServers`, `strictKnownMarketplaces`, `disableSkillShellExecution`); `verify_deployed.py` as a SessionStart hook writing a FACT; `governance/ai-inventory.md` (role → tools → data classes → Rule-of-Two legs → HITL points); signed releases. *Why:* a misplaced managed key is silently ignored — the worst failure mode a control can have; ISO 42001 / NIST AI 600-1 / EU AI Act Art. 4 all require the inventory; SLSA L2 for our own artifacts is what we already demand of dependencies.

### 4.12 `/product-planning` (spec: v3.1 §4.12, ADR 0002)
**Built:** all 8 skills; story types with tier floors; AC standard (`ST-n/AC-n`, G/W/T, kind, verification, tags); DoR (28 items) and DoD (18 items + spike variant + ACCEPTED) as control-file YAML with STRUCTURAL/JUDGMENT/APPROVAL kinds; `plan_lint.py` (schema, refs, no-status, AC-freeze diff), `readiness_gate.py`, `completion_gate.py`, `ac_coverage.py` (title/`@ac` comment/JUnit name; characterization excluded); worked example with expected outputs; MCP `work_planning` (`ingest_plan_commit`, `evaluate_readiness`, `evaluate_done`, `query_work_graph`, `link_change_set`, `ingest_work_event`).
**Enforcement:** schema/no-status/AC-freeze — *Enforced* as scripts (31 tests); READY/DONE derived — *Enforced* in scripts, **but** the evidence they consume has no producer (exporter missing) and the MCP `ac_hash` ≠ the gate `ac_hash`; tracker projection — *Guideline* (job absent); policies as control files — *Enforced* on Claude Code.
**v4 decision:** shared `ac_hash`; `export-planning-evidence`, `record-planning-status`, `ingest-ac-coverage` in `ledger_cli.py` against existing APIs; `tracker_projection.py`; single-repo `planning` role defaults to the app repo; regenerate `examples/plans/evidence/evidence.json` from the real exporter in a test. *Why:* the layer's design is the strongest in the platform and should not change; it is blocked purely by two integration gaps. Hand-written evidence (today's fixture) is exactly the agent-authored evidence the platform forbids, so the example must come from the exporter.

### 4.13 Test engineering & test data — see 4.8. Spec unchanged (v3.1 §4.13, ADR 0003).

### 4.14 Workflow stages & workspace (spec: v3.1 §4.14, ADR 0004)
**Built:** `stages.yaml` (10 stages, inputs with `required: always|never|tier>=X|existing_repo`, backfill targets, exit gates, lead roles, degraded mode); conductor with request grammar and checkpoint schema; `ingest_documents.py` (section hashes, source register, diff mode); `resolve_workspace.py` (roles app/planning/tests/contracts/infra, FOUND/AMBIGUOUS/MISSING, `--init-local`, `--request-remote`); `stage_preflight.py` (all 13 artifact-kind checks, intake coverage, workspace section, degraded routing); brownfield `import_tracker.py`; `create_repo_from_request.py` (human/CI only) + `templates/repo-bootstrap/`.
**Enforcement:** gates between stages — *Enforced* by CI scripts where they exist, *Guideline* in the conductor (honestly stated); remote repo creation human/CI-only — *Enforced* by interlock; "never skip a gate" — depends on CI wiring per repo.
**Gaps:** single-repo `planning` resolves MISSING; `--existing-repo no`, `--tier`, `--mode characterization` are caller switches recorded as evidence; Windows console encoding (PLAUSIBLE).
**v4 decision:** fix the single-repo default; derive `existing_repo` from the resolver only and record any override as RISK; `sys.stdout.reconfigure(encoding="utf-8")` in every script; validate `checkpoint.json` in CI so a run that skipped a gate cannot resume. Keep the five-outcome vocabulary and the stage graph. *Why:* preflight output is advisory to the agent but is also recorded — the recorded form must be non-gameable; the stage model itself is right (starting late skips work, never gates).

### 4.15 Existing project standards (spec: v3.1 §4.15, ADR 0005) — see 4.9. Unchanged.

### 4.16 Stack-agnostic repository understanding (new in v4 — consolidates scattered scanners)
**Problem:** five scripts parse manifests independently (`stack_fingerprint.py`, `convention_scan.py`, `scan-imports.py`, `resolve_workspace.py`, `stage_preflight.py`) with five different manifest lists and no monorepo awareness; the MCP server has its own path-tier table; AC hashing is duplicated.
**Decision:** one stdlib library `skills/core/repo-facts/` with:
- `manifests.py` — Renovate/Dependabot-parity tables (incl. `deno.json`, `bun.lock`, `Podfile`, `MODULE.bazel`, `Directory.Packages.props`, `gradle/libs.versions.toml`, `pnpm-workspace.yaml`, `uv.lock`, `Chart.yaml`, `*.tf`, Dockerfiles, devcontainer locations);
- `workspace.py` — workspace walker (`package.json#workspaces`, `pnpm-workspace.yaml`, `settings.gradle` includes, `.sln`, Cargo workspaces, melos) → `packages[]` with per-package stack and toolchain;
- `exclusions.py` — vendored/generated detection (`.gitattributes linguist-*`, standard dirs) so counts are right;
- `tiers.py` — the single path-tier evaluator; `achash.py` — the single AC hash; `canon.py` — canonical JSON;
- outputs `stack.json`, `conventions.json`, `workspace.json`, and (new) `system-map.json` for multi-repo ingestion (OpenAPI/AsyncAPI/proto files + env/hostname literals + Backstage `catalog-info.yaml` + optional OTel servicegraph import), all hash-anchored in the ledger.
The four existing scanners become thin consumers; the MCP modules import the same package. A thin `/workflow/system-ingestion` skill drives multi-repo ingestion.
**Why this and not alternatives:** (a) *LLM reads the repo* — non-deterministic, un-cacheable, token-costly, contradicts the FACT model; (b) *tree-sitter/SCIP as the engine* — SCIP needs a build; tree-sitter is a good optional second pass for symbols but overkill for presence detection; (c) *keep five parsers and sync by hand* — divergence has already happened in every duplicated spot. Renovate and Nx prove that glob tables + workspace walking is the right fast first pass; the difference is their tables are 10× larger. Tree-sitter is adopted as an optional structure pass (Aider repo-map style), never as a precondition.

---

## 5. Cross-Cutting Design Rules — with reasoning

### 5.1 Evidence taxonomy
FACT (hook-written, source required) · INFERENCE (`input_references` required; inherits lowest trust) · ASSUMPTION (impact + `expires_at`) · QUESTION (`blocking`, OPEN/ANSWERED/EXPIRED) · DECISION · RISK · PROPOSAL; lifecycle PROPOSED → REVIEWED → VERIFIED/APPROVED; corrections are new entries (CHALLENGED), never edits. *Why:* the classification is stored, not re-inferred, so an ASSUMPTION crafted to read like a FACT stays an ASSUMPTION (AAT-ASI06-010).

### 5.2 Ask vs. assume
Blocking ambiguity → QUESTION with a proposed default (never empty-handed), batched once per story/run; tolerable gap → ASSUMPTION with impact and expiry; HIGH/CRITICAL block on open questions. *Why:* unbatched questions stall runs; empty-handed questions push work onto the human; unexpiring assumptions become facts by neglect.

### 5.3 Fail-safe defaults
Tier unknown → HIGH; compatibility unknown → INCOMPATIBLE; dependency unprovable → UNRESOLVED; two roles disagree → higher wins; hook timeout → CI backstop re-checks (v4). *Why:* see §1 #5; the hook-timeout rule is new because both vendors fail open on timeout — the CI gate is the only backstop we control.

### 5.4 Risk tier → gates
Effective tier = max(story-type floor, path tier of affected/changed paths, declared tier, reason-code escalation of exactly one level). Gates: LOW `ci`; MEDIUM + `unit-tests` (+ `mutation`, v4); HIGH + `sast`, `sca`, contract analysis, security-reviewer, reviewer diversity; CRITICAL + staged rollout, product-owner + security-lead approval. Control-file path → CRITICAL always. Downgrades human-only and logged. *Why:* "scale process to risk" needs a monotone, computable function; every input can only raise, so no agent statement lowers scrutiny.

### 5.5 Authority: REVIEWED / VERIFIED / APPROVED
Unchanged (§1 #3). v4 adds the missing mechanism: a SYSTEM write path (`ledger_cli.py record-gate` for CI identity; later HTTP transport) so VERIFIED is reachable. *Why:* an authority level with no producer is theoretical; the DoD's `tier_gates_verified` cannot pass without it.

### 5.6 Skill execution model — rule → enforcement point
The enforcement map becomes three columns: **Enforced** (artifact + test), **Detects**, **Guideline**. A CI check requires every Enforced row to name a test that exercises the block, and every SKILL.md `## Enforcement` section to use one of three fixed phrases. *Why:* this is the single most important fix in v4 — the platform's value is the distinction, and the distinction was being blurred by its own documentation.

### 5.7 Agent failure handling
Failure catalog (RETRY ≤3 / REPLAN / ESCALATE / STOP) unchanged; v4 maps the attempt cap to subagent `maxTurns` and to `tasks[].attempts` in the Change Set, and records permission denials as ESCALATE never RETRY. *Why:* `maxTurns` is the only cap the runtime enforces regardless of model behaviour.

### 5.8 Identity & authentication
Server-derived identity from the credential; one credential per role; v4 adds `expires_at`, revocation, and derives `source_type` from the hook's observed tool event (signed with the hook token) rather than the caller's payload. *Why:* v3 moved forgery from `trust_level` to `source_type`; closing it the same way (server-derived) is consistent. CISA 2026: short-lived credentials per agent.

### 5.9 Trust boundaries: the Rule of Two (Meta, 2025)
No session holds all three of: untrusted input, secrets/production data, external mutation/deploy. Per-role legs are documented in `governance/permission-scoping` and (v4) in `governance/ai-inventory.md`; the developer role keeps Bash only inside the vendor sandbox with a filesystem allow-list equal to Change Set scope. *Why:* the sandbox is the vendor's enforcement primitive; writing our own shell parser is an arms race we lose (the guard's own docstring says "obvious writes only").

### 5.10 Forge as source of truth
INTEGRATED = observed merge; RELEASED = deployment record + environment approval; APPROVED = CODEOWNERS-gated review; ROLLED_BACK = observed revert. A merge observed while criteria fail is recorded **and** raises a RISK (admin bypass is visible, not hidden). v4: approvals are epoch-scoped to the plan they approved. *Why:* ITIL/SOC 2 — authorization attaches to a specific assessed change.

### 5.11 Catalog outputs are evidence, so they are anchored (new)
`.adlc/catalog/*.json`, `.adlc/ingest/*`, `.adlc/runs/*/checkpoint.json` are hook-written FACTs with content hashes recorded in the ledger; gates verify the hash before trusting a file; integrity overrides come from ledger REVIEWED entries, never from a file in the PR head. *Why:* every gate trusts these files and every agent can write them; making `.adlc/**` a control file would block the scripts agents legitimately run, so hash-anchoring is the smallest fix that makes tampering detectable.

### 5.12 Platform supply chain and authorship (new)
Platform releases (skills as plugins, `dist/`, MCP server) are signed (Sigstore keyless) with in-toto/SLSA v1.1 L2 provenance and a CycloneDX SBOM; marketplaces pinned (`strictKnownMarketplaces`). Commits produced under the platform carry `Co-Authored-By:` (vendor default) plus `ADLC-Run: <run_id>` trailers; CI checks presence; the human author remains accountable and the human approver is distinct from the authoring agent. *Why:* OWASP ASI04 and the 2026 GitGuardian data put the platform itself on the attack surface; SOC 2 CC8.1 needs request → approval → review → test → deploy linked to a principal — the trailer links commit to ledger run.

---

## 6. MCP Server — as built and target

**As built (ADR 0001):** one server `adlc`, stdio transport, SQLite per module under `.adlc/` (relative to cwd by default), kernel = identity (token → actor_type/role/tool/model, hashes only stored), config, db (append-chained rows, `verify_chain`), vocab, errors, mcp_compat. Modules each with `api.py` (business API, identity-checked), `domain.py`, `store.py`, `tools.py`, `migrations/`; ports wired in `app.py`; AST test forbids cross-module imports. 82 tests pass.

**Tools registered today (31):**
- evidence_ledger: `record_evidence`, `query_evidence`, `record_correction`, `record_handoff`, `record_incident`, `query_incidents`, `record_lesson`, `query_lessons`
- change_management: `create_change_set`, `get_change_set`, `update_status`, `ingest_forge_event` (SYSTEM), `create_snapshot`, `validate_snapshot_currency`, `record_dependency`, `compute_risk_tier`, `override_risk_tier` (HUMAN), `record_task`, `checkpoint_task`, `record_task_failure`
- contract_registry: `register_contract`, `record_deployment` (SYSTEM), `check_compatibility`, `detect_drift`
- work_planning: `ingest_plan_commit`, `evaluate_readiness`, `evaluate_done`, `get_work_item`, `query_work_graph`, `link_change_set`, `ingest_work_event`
- CLI: `ledger_cli.py append-fact | verify | purge | query`; `adlc_credentials.py`

**Target (v4), in priority order, with reasoning:**

| Change | Why |
|---|---|
| **Workspace anchoring:** `workspace_id` derived from `adlc.workspace.yaml` or the repo remote; one DB set per workspace; every write requires `change_set_id` or `story_id`; references validated; response envelope `{ok, scope, as_of, data, warnings, error}`; SQLite WAL | The three-amigos protocol *requires* three concurrent sessions. Without scoping they read each other's state. Per-workspace DB is the smallest change that gives isolation without a server rewrite; the envelope lets callers detect scope mismatches. |
| **SYSTEM write path:** `ledger_cli.py record-gate / record-review / export-planning-evidence / record-planning-status / ingest-ac-coverage` for CI identity; later streamable-HTTP transport with OAuth 2.1 + RFC 8707 resource indicators + RFC 9728 metadata for CI/webhooks | VERIFIED has no producer today. CLI first because CI already runs Python; HTTP when webhooks need to push forge events. |
| **`source_type` server-derived** from the hook event, payload signed with hook token; `ADLC_REQUIRE_HOOK_TOKEN=1` default | Caller-chosen trust is the v3 flaw moved one field left. |
| **Role-scoped tool registration server-side** from a JSON `role-tool-permissions`; `AGENT_ROLES` generated from `roles/*/role.yaml` (adds product-planner, test-engineer) | Client tool lists are REPOSITORY-trust config; two v3.1 roles cannot authenticate today. |
| **MCP 2026-07-28 alignment:** tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`), `outputSchema` structured results, `ttlMs`/`cacheScope` on list results, `server/discover`, OTel `traceparent` in `_meta`; design doc rewritten (no sessions/`Mcp-Session-Id`, no `resources/subscribe`) | Clients use annotations to decide confirmation UX; structured output lets hooks validate; the current design doc describes removed protocol features. |
| **Lifecycle hardening:** `approval_epoch`; BLOCKED exits defined for every state; property tests over the transition table; shared tier table | Approval of plan N ≠ approval of plan N+1; untested edges (merge while FAILED) are where audits bite. |
| **Credential lifecycle:** `expires_at`, revoke list, SessionStart refusal | CISA 2026 short-lived credentials. |
| **Redaction before write** in `fact_writer` (digest + head for file reads; secret/PII regex); server-side read-deny on `query_evidence` by caller role | The ledger must not be a secret store or a blindness bypass. |
| Extraction stays possible: each module keeps its own DB file and port; the boundary test stays. | Keeps ADR 0001's promise without paying for three services before the pilot proves the need. |

**Concurrency semantics (agreed design):** optimistic concurrency via `as_of`/row version on reads that feed writes; task leases (`checkpoint_task` holds a lease; a second session gets `warnings: ["lease held by …"]`); change feed (`query_evidence --since cursor`) for cross-session sync; writes never block reads (WAL). *Why:* agents coordinate through the ledger, not through locks; leases plus a feed give "where needed in sync" without a scheduler.

---

## 7. Pilot & Measurement

Unchanged definitions (`docs/pilot-measurement.md`): five baselines (lead time, change-failure rate, rework rate, review time, cost per merged change), override rate, planning health (DoR escape rate, split-after-READY, size calibration, AC coverage at DONE), test health (integrity findings/PR, escaped defects in agent-tested code, mutation trend, new-test flake rate).

**v4 additions:** DORA instability signal (deploy frequency vs CFR); PR size, review-wait and no-review-merge rates (the Faros/LinearB 2026 indicators); token cost per merged change from ledger `model_id` + usage fields; one perceptual SPACE/DX signal (reviewer satisfaction survey, quarterly). `tools/metrics_export.py` produces all tables weekly from forge API + ledger. *Why:* DORA 2025 puts measurement first among seven AI capabilities, and 2024–26 data shows AI raises throughput while lowering stability — a pilot that only measures speed will declare victory wrongly. Exit criteria must be written before the first Change Set (template §6).

---

## 8. Tool Compatibility — Claude Code / GitHub Copilot (2026-10)

Verified against vendor docs on 2026-10-03; a CI "spec currency" check (pinned doc version, max age) is added so this section cannot silently rot.

| Concept | Claude Code | GitHub Copilot | Platform rule |
|---|---|---|---|
| Skills | `.claude/skills/<name>/SKILL.md`; frontmatter `name`, `description`, `when_to_use`, `paths`, `allowed-tools`, `disable-model-invocation`, `hooks`, `metadata`…; description+when_to_use first ~1,536 chars shown, listing truncated at ~1% of context | `.github/skills/` (also reads `.claude/skills/`); loaded "when relevant" | Descriptions ≤160 chars, triggers first; `paths:` on every stack skill; mandatory policy in hooks/CI, never in descriptions |
| Roles | `.claude/agents/*.md` (camelCase: `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks` PreToolUse/PostToolUse/Stop, `memory`, `isolation: worktree`); inherit `permissions.deny` | `.github/agents/NAME.agent.md` (`name`, `description`, `tools`, `model`, `target`, `disable-model-invocation`, `mcp-servers`; `handoffs`/`argument-hint` VS Code-only; prompt ≤30k chars); "coding agent" is now **Copilot cloud agent** | Generated by `generate_agents.py` from `role.yaml`; add `maxTurns`, `disallowedTools`, `isolation` |
| Hooks | Events incl. `SessionStart`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, `InstructionsLoaded`, `ConfigChange`, `SubagentStart/Stop`, `PreCompact`…; PreToolUse → `hookSpecificOutput.permissionDecision: allow|deny|ask|defer` + reason; exit 2 blocks; **timed-out hooks fail open** | `.github/hooks/*.json` (`version: 1`); `preToolUse` → `permissionDecision: allow|deny|ask`; **cloud agent treats `ask` as `deny`, runs bash hooks only, fails open on timeout** | Target the common subset; every hook-enforced rule has a CI backstop; `adlc_enforcement.parse_event` normalises stdin |
| Managed settings | `managed-settings.json` (OS path / MDM / console); `permissions.allow/deny/ask/defaultMode`, `permissions.disableBypassPermissionsMode: "disable"`, `allowManagedPermissionRulesOnly`, `allowManagedHooksOnly`, `allowManagedMcpServersOnly`+`allowedMcpServers`, `strictKnownMarketplaces`, `disableSkillShellExecution` | Org policies + rulesets; CLI policy hooks `/etc/github-copilot/policy.d/` cannot be disabled | Template regenerated with verified key placement; `verify_deployed.py` SessionStart check |
| Path denials | `Edit/Write/Read(<glob>)` deny rules — enforced for file tools, **not** for Bash | **None.** Agent files carry denies as prose | Blind roles (qa-derive) and reviewer roles run on Claude Code with managed denies, or in a sandboxed runner; on Copilot they are *instructed only* and the docs say so |
| AGENTS.md | Native via `agents-md@builtin`; default `claude-md-or-agents-md` (AGENTS.md ignored if a CLAUDE.md exists unless it imports `@AGENTS.md`); `.claude/rules/*.md` with `paths` | Reads nearest `AGENTS.md`/`CLAUDE.md`; `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` with `applyTo` | AGENTS.md source of truth + one-line `CLAUDE.md` shim; CI `check_agents_md_shim.py` |
| MCP | Spec 2026-07-28: stateless (no sessions), `server/discover`, tool annotations, structured output, MRTR replaces elicitation/sampling, OAuth 2.1 + RFC 8707 + CIMD | Same client | `adlc` upgraded per §6 |
| Handoffs | Subagent delegation at runtime; `record_handoff` for durability | Native handoffs unsupported on cloud agent | `record_handoff` via MCP everywhere |
| Cloud agent limits | — | One repo/branch/PR per task; 59-min cap; cannot approve/merge own PR; Actions need human approval; firewall allow-list | Copilot cloud agent runs developer/test-engineer tasks only; planning, review and blind roles run on Claude Code |
| Packaging | Plugins: `.claude-plugin/plugin.json`, `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json`; marketplace manifest | `.github/skills`, `.github/agents` in `.github`/`.github-private` org repos | Each `skills/<group>` is a plugin; enforcement ships from a managed source only |

---

## 9. Build Sequence — status and remediation order

Checkbox = exists and is tested; `~` = exists, gap noted; `☐` = absent.

| # | Item | Status | v4 action (why) |
|---|---|---|---|
| 1 | Control-files definition + managed-settings denial | ~ | Split platform/target categories; verify key placement (misplaced keys are silently ignored) |
| 2 | AGENTS.md + CLAUDE.md shim + CI check | ☑ | — |
| 3 | `/core` + `/grounding` + `/enforcement` | ~ | Redaction in fact-writer; handoff schema validation; three-column enforcement map |
| 4 | Evidence Ledger (module of `adlc`) | ~ | SYSTEM write path; workspace anchoring; `source_type` derivation; expiry |
| 5 | Path-based risk tier lookup | ~ | Single table via `repo-facts` (two engines disagree today) |
| 6 | `/governance/default-permissions` | ~ | Role denies into managed template; AI inventory |
| 7 | `/skill-routing` | ~ | `route.py` + `paths:` frontmatter (policy-loaded, not LLM-chosen) |
| 8 | Minimum `/roles` + handoff + conflict resolution | ☑ | Regenerate with `maxTurns`/`disallowedTools`/`isolation`; Copilot limits stated |
| 8a | Product planning core | ~ | Shared `ac_hash`; exporter/status/coverage CLI; tracker projection; single-repo default; regenerate example evidence |
| 9 | `/self-improvement` | ~ | Unify schemas; sanitizer tests |
| 9a | Test engineering core | ~ | Ship red/green, flake gate, mutation adapters, impact-plan check; overrides from ledger; shared preflight reference |
| 10 | Security + AI-agent testing | ~ | Harness for ASI03/ASI02 catalogs in CI |
| 11 | `/change-management` + module | ~ | Approval epochs; BLOCKED exits; property tests; wire dependency-decision-check |
| 12 | `/testing`, `/engineering-design`, `/ai-integration` progressive | ~ | Fingerprint to Renovate parity; workspace walker; description/size budgets |
| 13 | `/contracts` + module + remaining roles | ~ | Phase 3 wiring unchanged |
| 14 | Pilot metrics baseline | ☐ | `metrics_export.py`; exit criteria signed before first Change Set |
| 15 | Tool-specific generator | ☑ | Add spec-currency check |
| 16 | **(new)** `repo-facts` engine + `/workflow/system-ingestion` | ☐ | Build; four scanners and two MCP modules import it |
| 17 | **(new)** Signed releases, SBOM, SLSA L2, marketplace pinning | ☐ | Release workflow |
| 18 | **(new)** AI-authorship + run-id trailers, CI check | ☐ | Small; links commit → ledger |
| 19 | **(new)** Enforcement-claim CI check (Enforced rows must name a test; `## Enforcement` uses fixed phrases) | ☐ | Makes §5.6 self-policing |
| 20 | **(new)** Skill catalog consolidation 83 → 31 (review Appendix B), one reviewed PR; descriptions ≤160 chars, shared preflight reference, `paths:` on stack skills, rules files generated | ☐ | Fits the skill-listing budget; removes trigger overlap and boilerplate drift; done **before** 10–18 so enforcement wiring targets final paths |

**Order (one engineer, ~8–10 weeks):** P0 items from the review §8 (1–9) → **catalog consolidation (20)** → `repo-facts` + routing → test-integrity gates → MCP 2026-07-28 + HTTP → signing/trailers/metrics → P2 polish. **Rationale for the order:** P0 makes the headline journey (documents → READY → DONE) actually run and removes the three ways evidence can be forged (`.adlc/**`, `append-fact`, raw content); consolidation comes next because every later item references skill paths; `repo-facts` fixes correctness of routing for every stack; test gates make the oracle promise real; protocol/supply-chain work is needed for enterprise adoption but not for the first pilot.

---

## 10. Decision Log — what we rejected and why

| Rejected | Reason |
|---|---|
| Three separate MCP services | No evidence of scale need; triples auth surface; extractability already enforced by the boundary test. |
| PyYAML/pydantic in CI scripts | Loses the "any Python 3.10, no venv" property that makes gates deployable in any CI; add parity tests to `minyaml` instead. |
| `.adlc/**` as a control file | Blocks the discovery scripts agents must run; hash-anchoring outputs achieves tamper-evidence instead. |
| A complete shell-command parser in the control-file guard | Arms race; the vendor sandbox is the enforcement primitive. |
| LLM-based stack detection | Non-deterministic, un-cacheable, token-costly; contradicts the FACT model. |
| SCIP/LSP as a precondition for repo understanding | Needs a build; fine in CI as an optional precision pass, never on the fast path. |
| Story points / velocity | Agent estimates are uncalibrated; predicted-diff size with calibration is strictly more useful. |
| Characterization tests counting as AC coverage after review | Reopens "code is the oracle"; graduation path (add AC later) already exists. |
| Native Copilot handoffs | Unsupported on cloud agent; `record_handoff` is already the durable path. |
| Pretending Copilot path denials exist | ASI09 applied to our own docs; route blind roles to where the control holds. |
| Building all 25 enforcement points before any pilot | Months of delay; honest three-column labelling costs a day and is itself a control. |
| "Short abstract notes only" for self-improvement (the original ask) | Cannot be run, cannot regression-test, invites vague fixes, can still leak; lesson + synthetic red/green reproduction keeps the sharing property and adds executability (ADR 0006). |
