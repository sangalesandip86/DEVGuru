# DEVGuru AI ADLC Platform — Full Review (brutal, evidence-based)

- **Date:** 2026-10-03
- **Reviewer stance:** expert AI-ADLC platform builder, prompt/skill author, MCP implementer; domain experts (test engineering, security, planning, architecture) where each section needs them.
- **Scope:** every file under `skills/`, `docs/`, `dist/`, `templates/`, `examples/` (83 SKILL.md, 108 Python files, 4 MCP modules, 6 ADRs, plan v3/v3.1), read by me end to end. Five earlier read-only audits (~170 findings) and two web-research reports (enterprise standards; stack-agnostic detection) are folded in. Where I could not re-verify an audit finding by reading code, it is marked **PLAUSIBLE** and needs a test; everything else is **CONFIRMED** against the file cited.
- **Companion:** [`../ai-sdlc-platform-plan-v4.md`](../ai-sdlc-platform-plan-v4.md) — the plan rewritten to match what is actually in this folder, with the remediations below folded in.

The format of every finding is: *what*, *evidence*, *why it matters*, *recommendation*, and **why that recommendation is the best option** (alternatives considered). Where the recommendation is "keep as is", the reasoning says why the existing design is the right one.

---

## 0. Verdict in one page

**What this platform gets right that almost nothing in the market does:** it separates *what the agent is told* from *what the platform enforces*, and it is honest about the difference. Authority is split REVIEWED (agent) / VERIFIED (server, machine evidence) / APPROVED (human). The test oracle is derived code-blind and frozen to an AC hash. Plans are code, status is derived by gates, and no agent tool can set READY/DONE/INTEGRATED/RELEASED. Control files are a named trust category. Convention discovery is deterministic. Self-improvement is human-gated and lesson-based. Those design decisions line up with every 2026 enterprise standard the research found (OWASP ASI, CISA/NSA agentic guidance, ISO 42001 life-cycle controls, SOC 2 separation of duties, DORA's "small batches + strong version control", Thoughtworks' "feedforward skills + feedback mutation testing"). **The architecture is credible. Keep it.**

**What is wrong:** the platform *claims* about 40 enforcement points and *delivers* roughly a third of them. The rest are either guidelines wearing enforcement language, or enforcement with a hole in it (Bash bypass, Copilot has no path denials, hooks fail open, `append-fact` is forgeable, `.adlc/**` is agent-writable while every gate trusts it). Two independent implementations exist for the same contract in at least five places (AC hash, path tiers, manifest parsing, ledger schema, incident schema), and they disagree. The headline user journey — *documents → ARCHITECTURE → PLAN → READY story* — cannot complete end to end today because three CLI commands the gates depend on do not exist. Zero pilot evidence exists; every "this works" is a passing unit test on synthetic data.

**Scores (0–5, enterprise bar = 4):**

| Area | Score | One-line reason |
|---|---|---|
| Architecture & authority model | 4.5 | Right split; matches 2026 guidance; one hole (VERIFIED unreachable in ledger) |
| Enforcement reality | 2 | ~⅓ of claimed rows actually enforce; Bash/Copilot/hook-timeout holes; forgeable FACTs |
| MCP server | 2.5 | Clean modular monolith, good tests, but stdio-only, no sessions/workspaces, no annotations, duplicated contracts, outdated vs MCP 2026-07-28 |
| Evidence Ledger | 3 | Append-only hash chain is solid; trust derived from caller-supplied `source_type`; raw file content stored (secrets) |
| Planning layer | 4 | Best-designed layer; blocked by ac_hash divergence and missing evidence exporter |
| Test engineering | 3.5 | Oracle/binding split is excellent; red/green, flake gate and mutation are stubs, so the headline guarantee is paper |
| Workflow / any-stage entry | 3 | Good model; e2e path dead-ends; single-repo planning MISSING; tier is agent-declarable |
| Stack-agnostic detection | 2.5 | Right shape, pattern tables ~10× too small, no monorepo walk, root-only toolchain |
| Roles & tool compatibility | 3 | Good generator; Copilot denials are prose; Claude subagents inherit deny only if managed; outdated hook/MCP spec references |
| Skills as prompts | 3.5 | Consistent, honest "guideline only" labels; too long, duplicated preflight blocks, descriptions over the routing budget |
| Self-improvement | 3.5 | ADR 0006 design is right; schema ≠ MCP implementation; lint stubs |
| Governance / supply chain / measurement | 2 | No signing/SLSA for the platform itself; AI-authorship trailers absent; pilot metrics are a blank template |
| Documentation integrity | 2.5 | Enforcement map overclaims; README build status wrong; design doc cites nonexistent denies |

**Overall: 3.1 / 5.** Credible design, pre-pilot implementation. Not shippable to a regulated enterprise until the P0 list in §8 is done — and those are mostly days, not months, because the architecture does not need to change.

---

## 1. Method and honesty statement

1. I read every file personally (previous summaries delegated reading; the user challenged that; this document is after the full read).
2. Three test suites pass today: enforcement (40), MCP server (82), planning gates (31); `check_skill_contracts.py` passes 83/83. These prove internal consistency of each island, not integration between islands — which is where most findings sit.
3. Each finding cites a path. If I say "does not exist" I grepped for it. If I say "PLAUSIBLE" I am relaying an audit and could not reproduce from code alone.
4. Research inputs (2026-10-03): OWASP Top 10 for Agentic Applications v1.0 (Dec 2025); OWASP LLM Top 10 2025; Meta "Rule of Two" (Oct 2025); CISA/NSA/Five Eyes agentic adoption guidance (Apr 2026); NIST AI 600-1; ISO/IEC 42001; EU AI Act Digital Omnibus (Jul 2026); SLSA v1.1; DORA 2024/2025/2026 and the AI Capabilities Model; ISO/IEC/IEEE 29148 and 29119-4; Faros/LinearB/GitClear AI-PR data; Claude Code hooks/skills/subagents/managed-settings docs; Copilot custom-agents/hooks/skills docs; MCP spec 2026-07-28; Linguist, Renovate, Dependabot, Nx, Turborepo, tree-sitter, SCIP, Aider repo-map.

---

## 2. What is genuinely best-in-class — keep, and why

These are decisions I would defend against any reviewer. Reasoning given because the user asked for it explicitly.

| Decision | Where | Why it is the best option (alternatives rejected) |
|---|---|---|
| **Three-way authority** REVIEWED / VERIFIED / APPROVED, with VERIFIED only from machine evidence | plan §5.5, `kernel/identity.py`, `evidence_ledger/domain.py` | Two-level systems (agent vs human) let an agent's "I verified it" count as verification; that is exactly the "almost right code" trust collapse in the 2025/2026 Stack Overflow surveys. CISA 2026 says agents must not decide which of their own actions need sign-off. The three-way split is the minimum that encodes that. |
| **Forge events as source of truth** for INTEGRATED / RELEASED / APPROVED (`ingest_forge_event`, SYSTEM-only) | `change_management/api.py:140` | The alternative (a custom state machine agents move) is what v2 had and what every audit framework (SOC 2 CC8.1, ISO 27001 A.8.32) would reject: the merge, the deploy and the CODEOWNERS review are the audit evidence auditors already accept. Observing them instead of re-stating them removes a whole class of forgery. |
| **Oracle/binding split**: qa-derive code-blind writes the frozen design; test-engineer binds it; expectation changes require an AC-hash change | ADR 0003, `test-case-design`, `suite-authoring`, `test_integrity_guard.py` | Research is unambiguous: LLM tests reach 100% coverage with 4% mutation score and agents "fix" red builds by editing expectations. Blinding the oracle is the only structural (not instructional) defence. Alternatives — "tell the agent not to peek", or post-hoc review — are advisory and fail under pressure. |
| **Plan-as-code with derived status; `additionalProperties:false` makes `status:` a schema error** | `product-planning/schemas/*.json`, `plan_lint.py` | Trackers let anyone drag a card to Done. Deriving READY/DONE from a gate over the merged plan + ledger means the status *is* the evidence. Making the field a schema error (not a lint warning) removes the temptation entirely. |
| **Control files as a trust category, denied at managed-settings level** | `control-file-paths.json`, `generate_deny_list.py`, `control_file_guard.py` | The 2025–2026 incident record (CurXecute mcp.json rewrite, "Comment and Control", 24k secrets in MCP configs) is entirely "agent rewrites its own config". Prose cannot stop it; a managed deny list plus a PreToolUse hook can. |
| **Fail-safe defaults**: unknown tier → HIGH; unknown compatibility → INCOMPATIBLE; unknown dependency → UNRESOLVED | `path_tier_lookup.py`, `check-can-i-deploy.py`, `scan-imports.py` | Every alternative default ("assume fine") converts missing evidence into permission. Fail-closed is the only default that makes "we didn't know" auditable rather than exploitable. |
| **Deterministic discovery scripts before any LLM judgement** (stack fingerprint, asset catalogue, convention scan, boundary values) | `stack_fingerprint.py`, `test_asset_catalog.py`, `convention_scan.py`, `boundary_values.py` | Zero-token, reproducible, cacheable per snapshot, recorded as FACT by hooks. An LLM "looking at a few files" guesses differently each run. This is how Renovate/Nx/Linguist work. Keep the shape; widen the tables (§5.G). |
| **Precedence ladder for brownfield work**: platform rules > declared standards > observed conventions > generic guidance; deviation = DECISION + ADR | ADR 0005, `project-conventions` | Faros 2026: AI PRs are +51% larger and review time +441%. Most of that is style drift and silent architecture change. Consistency-over-preference, with deviations as reviewable ADRs, is the cheapest way to make AI diffs reviewable. |
| **Self-improvement = sanitized lessons + synthetic red/green reproduction, human-gated** | ADR 0006 | Raw incidents leak customer data across projects; abstract notes alone cannot be run or regression-tested. Lesson + synthetic eval is the only form that is both shareable and executable. Choosing gates over prose, and a skill size budget, prevents the "accreting prompt" failure mode Anthropic's own best-practices doc warns about. |
| **Modular monolith MCP server** with AST-enforced module boundaries | ADR 0001, `tests/test_module_boundaries.py` | One deployable, one credential story, one install step — yet each module owns its DB and port and can be extracted. Three servers would triple the auth surface before any pilot proves the need. |
| **Degraded Mode** (missing agent role → named human stands in; never a silent skip, never an indefinite block) | plan §2, `stages.yaml → degraded_mode` | Phased builds deadlock without it. The alternative (gate off until the role exists) is what makes platforms unusable in month one. |
| **Preflight outcome vocabulary** SATISFIED / ADOPT / BACKFILL / ASK / BLOCK | ADR 0004, `stage_preflight.py` | Five outcomes is the smallest set that distinguishes "exists", "exists outside", "missing", "ambiguous", "failed". It makes any-stage entry safe: starting late skips *work*, never *gates*. |

---

## 3. Benchmark against enterprise standards and real pain points

| Standard / pain point (2026) | Requirement | Platform status | Gap |
|---|---|---|---|
| OWASP ASI03 identity & privilege | Each agent a distinct principal, server-derived identity, short-lived creds | Server-derived identity from `ADLC_TOKEN` ✔; one credential per role ✔; **no expiry / rotation**; credentials file is long-lived hashes | Medium |
| OWASP ASI02 tool misuse | Deny holds against indirect routes (shell) | `control_file_guard.py` inspects "obvious" shell writes only (its own docstring); role path-denies are Edit/Write only | **High** |
| OWASP ASI06 context/memory poisoning | Config/instructions integrity | AGENTS.md/CLAUDE.md shim check ✔; `.adlc/**` (catalogs, overrides, checkpoints) **not** a control path though every gate trusts it | **High** |
| OWASP ASI04 supply chain | Signed skills/plugins/MCP, provenance | Deferred; nothing signed; `strictKnownMarketplaces` not in template | Medium (pre-pilot acceptable, enterprise blocker) |
| Meta Rule of Two | No role holds untrusted input + secrets + external mutation | Designed ✔; **developer role has Bash + reads untrusted issues + network**; not sandboxed by the platform | Medium |
| CISA/NSA Apr 2026 | Agents must not decide their own sign-off; auth chains reconstructable | Authority split ✔; **tier is agent-declarable via `--tier`** on preflight; hooks time out fail-open (both vendors) | **High** |
| SOC 2 CC8.1 / ISO 27001 A.8.32 | request → approval → review → test → deploy chain; human approver ≠ author | Ledger + forge events give the chain ✔; `VERIFIED` is **unreachable** in the ledger via any shipped path (no SYSTEM MCP route, CLI only `append-fact`) | **High** |
| ISO 29148 traceability | ACs verifiable, IDs traced to tests | `ST-n/AC-n`, `ac_coverage.py` ✔ — best-in-class | — |
| ISO 29119-4 techniques | Design technique named | `technique` enum in test-design schema ✔ | — |
| Thoughtworks Radar 34 / mutation research | Mutation score, not coverage, gates AI tests | **Stub only** (`red_green_check.md`, `new_test_flake_gate.md` are prose; no mutation runner) | **High** |
| DORA 2025 AI Capabilities Model | Small batches; strong VCS; measurement | Diff cap 400 lines ✔ (only enforced when tier lookup runs); pilot metrics **blank template** | Medium |
| Faros/LinearB AI-PR data | Cap PR size, report no-review merges | Cap exists; no reporting | Medium |
| Claude Code spec (hooks 2026) | `hookSpecificOutput.permissionDecision`; `permissions.disableBypassPermissionsMode`; hooks fail open on timeout | Template nests `disableBypassPermissionsMode` at top level (**unverified key placement** — see F-H3); hook output format needs re-check; fail-open not acknowledged anywhere | Medium |
| Copilot spec (2026) | cloud agent: `ask`→`deny`, bash hooks only, no path-deny; `.agent.md` fields | Copilot agents carry deny lists as prose in body; `handoffs` referenced as unsupported ✔ | **High** on Copilot |
| MCP 2026-07-28 | sessions removed, `server/discover`, tool annotations, structured output, OAuth 2.1 + RFC 8707 | stdio only; no annotations/outputSchema; token via env var; design doc assumes older spec | Medium |
| Pain point: "almost right" code | Evidence-grounded claims, QUESTION not guess | evidence-gate ✔ — but **only a guideline** on free prose, honestly stated | — |
| Pain point: review overload | Reviewable diffs, conventions followed | conventions ✔; diff cap ✔; `code-design-reviewer` ✔ | — |
| Pain point: flaky/weak AI tests | Determinism controls, flake gate, mutation | Controls documented ✔; gates stubbed ✘ | **High** |
| Pain point: prompt injection via repo/CI | Structural containment | Designed ✔; tests catalogued ✔; **no harness runs them** | Medium |
| Pain point: token cost opacity | Cost per change | `model_id` on entries ✔; no cost field, no aggregation | Low |

---

## 4. Cross-cutting systemic findings (the ones that generate most of the rest)

### S1 — Enforcement language without enforcement points (CONFIRMED)
`docs/enforcement-map.md` lists ~25 "actually enforced by" rows. Reading the artifacts, these are **enforced today**: append-only hash chain; agent cannot write FACT/VERIFIED/APPROVED via MCP; `update_status` rejects agents; plan schema has no status; `readiness_gate.py`/`completion_gate.py`/`plan_lint.py` logic; `path_tier_lookup.py`; `test_integrity_guard.py` detection logic; `fixture_pii_scan.py`; `no_fixed_sleep_check.py`; Edit/Write denies for control files on Claude Code; shim check. These are **claimed but not enforced**: red/green (prose), mutation (nothing), new-test flake gate (prose), "no agent `EXTERNAL_MUTATION`" (no sandbox/network policy shipped), qa-derive blindness on Copilot and via Bash, 3-attempt cap (guideline, admitted), AC coverage → DONE (needs a nonexistent exporter), Rule of Two scoping (no runtime), tracker projection (job doesn't exist), impact-plan-vs-diff (no CI job), dependency-decision-check (exists but not wired to any gate), control-file CRITICAL on Copilot (prose).
**Why it matters:** the whole value proposition is "skills inform, hooks enforce". A reader of the enforcement map will deploy believing 25 controls exist. **Recommendation:** split the map into three columns — *Enforced (artifact + test)*, *Detects only (reports, no block)*, *Guideline* — and add a CI check that every "Enforced" row names a test that exercises the block. **Why best:** the alternative (build all 25 before pilot) delays the pilot by months; honest labelling costs a day and is itself a control (ASI09 human-trust exploitation applies to the platform's own docs).

### S2 — Duplicated contracts that disagree (CONFIRMED)
| Contract | Implementation A | Implementation B | Disagreement |
|---|---|---|---|
| AC hash | `planning-gates/ac_hash.py:40` (canonical *semantic* fields) | `work_planning/domain.py:46` (canonical_json of the raw AC list) | Different hashes for the same story → `evaluate_readiness` in MCP and `readiness_gate.py` in CI never agree; READY unreachable from one side or false freeze from the other |
| Path tiers | `risk-tiering/path-tiers.json` | `change_management/domain.py::_BUILTIN_PATH_TIERS` | Different rule sets (`*payment*` vs `**/payment/**`); two tiers for one diff |
| Ledger entry schema | `core/schemas/ledger-entry.schema.json` | `evidence_ledger/store.py` columns | Field names drifted |
| Incident / lesson schema | `self-improvement/*/schemas/*.json` | `record_incident` / `record_lesson` validation | Required fields differ |
| Manifest parsing | `stack_fingerprint.py`, `convention_scan.py`, `scan-imports.py`, `resolve_workspace.py`, `stage_preflight.py` | — | Five parsers, five different manifest lists |
**Recommendation:** one shared library `skills/core/repo-facts/` (manifests, tiers, AC hash, canonical JSON) imported by both CI scripts and MCP modules; CI test asserts hash equality on `examples/plans`. **Why best:** vendoring was chosen for stdlib-only portability, but divergence has already happened in every duplicated spot; a single import path with a cross-check test is cheaper than keeping five tables in sync by hand. Alternative (make the MCP server the only implementation and call it from CI) couples CI to a running server — rejected because CI gates must work offline on a PR.

### S3 — Everything trusts `.adlc/**`, nothing protects it (CONFIRMED)
`conventions.json`, `stack.json`, `test-assets.json`, `step-patterns.json`, `source-register.json`, `runs/<id>/checkpoint.json`, `integrity-overrides.json` live under `.adlc/` and are read by preflight, routing, and gates as FACT. `control-file-paths.json` does not list `.adlc/**`; agents can write it; `test_integrity_guard.py --overrides` accepts a file the same agent can author. **Recommendation:** (a) catalogs are hook-written FACTs — make `fact_writer` write them and have gates verify a content hash recorded in the ledger before trusting them; (b) `integrity-overrides` must come from the ledger (REVIEWED entries by qa-diagnose), never a file in `head/`; (c) `.adlc/catalog/**` and `.adlc/runs/**` become read-only to agents via the deny list, written only by hook/CI identity. **Why best:** making `.adlc/**` a control file outright would block the deterministic scripts agents legitimately run; hash-anchoring the outputs in the ledger keeps scripts runnable while making tampering detectable, which matches how the ledger already treats FACTs.

### S4 — Fail-open where it must fail closed (CONFIRMED + research)
Both Claude Code and Copilot hooks **fail open on timeout** (vendor docs, 2026). `ledger_cli.py append-fact` is accepted without a hook token unless `ADLC_REQUIRE_HOOK_TOKEN=1` (default off). `stage_preflight.py --tier` lets the caller declare a tier that *raises* only — good — but the agent can also omit `--story` and get `tier unknown → HIGH`, or pass `--existing-repo no` to skip the conventions requirement. **Recommendation:** default `ADLC_REQUIRE_HOOK_TOKEN=1`; preflight derives `existing_repo` from the resolver only; treat a hook timeout as a CI-side re-check (every hook-enforced rule also has a CI check — most already do). **Why best:** you cannot fix vendor timeout semantics; you can make the CI gate the backstop, which is already the stated model.

### S5 — The headline journey does not complete (CONFIRMED)
`planning-gates/README.md` and `workflow.example.yml` reference `ledger_cli.py export-planning-evidence`, `record-planning-status`, `ingest-ac-coverage` and `tools/tracker_projection.py`. `ledger_cli.py` has only `append-fact | verify | purge | query`. Without the exporter, `readiness_gate.py --evidence` has nothing real to read; without `record-planning-status`, `completion_gate.py`'s `ready_at_current_ac` can never pass; without the projection job, "agents never write the tracker; CI projects" is a promise with no implementation. Also `resolve_workspace.py` reports `planning: MISSING` for a single repo whose `plans/` is inside the app repo (ADR 0004 says that is the default). **Recommendation:** implement the three CLI subcommands against `evidence_ledger`/`work_planning` APIs (they exist), fix the single-repo default, and add an e2e test that runs `examples/plans` through ingest → preflight → readiness → completion using the real exporter. **Why best:** these are ~200 lines against APIs that already exist and are tested; the alternative (hand-written evidence JSON, as in `examples/plans/evidence/evidence.json`) is exactly the agent-authored evidence the platform forbids.

### S6 — "Technically denied" is Claude-Code-only and Edit/Write-only (CONFIRMED)
`settings.roles.json` and the managed template deny `Edit(...)`/`Write(...)` and, for qa-derive, `Read(src/**)`; `Bash` is denied to product-planner/qa-derive but **developer and test-engineer keep Bash**, and `cat src/x.py`, `git show HEAD:src/x.py`, `python -c "open(...)"` bypass a `Read` deny. On Copilot there is no path-deny primitive at all; the generated `.agent.md` carries the deny list as *text*. `control_file_guard.py` admits (docstring) it catches "obvious" shell writes only. **Recommendation:** (1) qa-derive: no Bash, period (already) — and make the ledger leak-proof (F-C4); (2) developer/test-engineer: Bash allowed but run inside Claude Code sandbox mode with a filesystem allow-list = Change Set scope; (3) Copilot: route qa-derive and reviewer roles to Claude Code or a sandboxed CLI runner only, and say so in `tool-compatibility.md`; (4) rename every "technically denied" statement that is Copilot-prose to "instructed (not enforced on Copilot)". **Why best:** the sandbox is the vendor's own enforcement primitive and already exists; writing a complete shell-command parser is an arms race you lose. Admitting Copilot's limit is cheaper and more honest than pretending.

---

## 5. Findings by area

Severity: **P0** blocks a credible pilot; **P1** blocks enterprise adoption; **P2** quality/consistency.

### A. Enforcement layer (`skills/enforcement/**`, `skills/governance/**`)

| ID | Sev | Finding | Evidence | Recommendation | Why this is best |
|---|---|---|---|---|---|
| A1 | P0 | `fact_writer.py` stores raw file-read content (up to 4000 chars, env-configurable) into the ledger with no redaction; `.env`, keys and tokens read by any role become ledger rows readable by `query_evidence` — including by qa-derive, which leaks implementation text around its path deny | `fact_writer.py:27-56`; `secret-scanning/SKILL.md` itself says "fact-writer hooks should redact" | Store digest + first line + byte count by default; full content only for `command_output`; run the gitleaks/PII regex set before write; add `source_path` so `query_evidence` can apply the caller role's read-deny globs server-side | A hash is enough for provenance (that is what the ledger is for); storing content turns the ledger into a secret store and a blindness bypass. Redaction before write is cheaper than retroactive purge of a hash-chained log you cannot edit. |
| A2 | P0 | `control-file-paths.json` lists `skills/**` and `dist/**`. In a *target* repo this denies writes to any folder named `skills/` or `dist/` (build output!) | `control-file-paths.json` categories | Split into `platform-repo` (skills/**, dist/**) and `target-repo` categories; `generate_deny_list.py --profile target` | Build output under `dist/` is the norm in JS/Python repos; a blanket deny will be the first thing a pilot team disables, taking the real controls with it. |
| A3 | P1 | Managed-settings template places `disableBypassPermissionsMode`, `allowManagedHooksOnly`, `allowManagedPermissionRulesOnly` — current docs show `disableBypassPermissionsMode` nested under `permissions`; the other two are top-level. Not verified against a live install; no `allowManagedMcpServersOnly`/`allowedMcpServers`, no `strictKnownMarketplaces`, no `disableSkillShellExecution` | template; vendor docs 2026-10 | Re-verify every key against the current settings reference in CI (a JSON schema fetched at build time or pinned); add the missing keys | A misplaced key is silently ignored — the control appears deployed and is not. That is the worst failure mode a managed setting can have. |
| A4 | P1 | `dependency-decision-check` exists but is not referenced by any stage exit gate, workflow example, or role | `stages.yaml`, `workflow.example.yml` | Wire into IMPLEMENT/REVIEW exit gate and `completion_gate` (`within_scope` or a new `deviations_declared` item) | A check nobody runs is a guideline. |
| A5 | P1 | `red_green_check.md`, `new_test_flake_gate.md` are Markdown; no mutation runner is shipped; `test-integrity/README` presents them as CI jobs | directory listing | Ship `red_green_check.py` (run new tests on base/head via runner adapters from `stack.json`), `flake_gate.py` (N random-order runs), and a mutation adapter table (Stryker/PIT/mutmut/cargo-mutants `--in-diff`) with a DoD `tier_gates` entry `mutation` at MEDIUM+ | Research: coverage without mutation is theatre for LLM tests. The platform *promises* this in 4 skills and the enforcement map. Either ship it or stop claiming it. |
| A6 | P1 | `check_control_file_policy.py` verifies the *template* content, not the *deployed* settings; `policy-drift-check` is a SKILL.md with no script | files | Add a `verify_deployed.py` that reads the OS managed-settings path and diffs; runs as a SessionStart hook writing a FACT | Drift between template and deployment is invisible today. |
| A7 | P2 | Copilot hook registration + `copilot-org-controls.md` are prose; no `.github/hooks/*.json` validation | `hooks/registration/copilot-hooks.json` | Add a schema check (`version: 1`, allowed events, bash-only for cloud agent) | Cloud agent treats `ask` as `deny` and only runs bash hooks — a Python hook silently does nothing there. |
| A8 | P2 | `planning-gates` tests pass, but no test runs the *CLI entrypoints* with the example tree (`WorkedExampleTest` imports functions) | `tests/test_planning_gates.py` | Add subprocess-based e2e over `examples/plans` | The README commands are what users run. |

### B. MCP server (`skills/mcp-servers/adlc-mcp/**`)

| ID | Sev | Finding | Evidence | Recommendation | Why best |
|---|---|---|---|---|---|
| B1 | P0 | No workspace/session anchoring: one `.adlc/` data dir relative to cwd; no `workspace_id` on entries; concurrent sessions on different projects from the same cwd share a ledger; `query_evidence` without `change_set_id` returns everything | `kernel/config.py` default, `evidence_ledger/store.py` | Adopt the routing design already drafted in-session: `workspace_id` derived from `adlc.workspace.yaml`/repo remote, DB per workspace, required `change_set_id` (or `story_id`) on every write, reference validation, `{ok, scope, as_of, data, warnings}` envelope, SQLite WAL | A single-process stdio server is fine for one dev; the moment two sessions run (the three-amigos protocol *requires* three sessions) it is a correctness bug, not a scale problem. Per-workspace DB is the smallest change that gives isolation without a server rewrite. |
| B2 | P0 | `VERIFIED` lifecycle state is unreachable: SYSTEM identity has no MCP path (stdio launched by the agent's client), and `ledger_cli.py` only exposes `append-fact` | `__main__.py`, `ledger_cli.py:35-40` | Add `ledger_cli.py record-gate` / `record-review` / `export-planning-evidence` for CI identity, or a second transport (streamable HTTP with OAuth 2.1 + RFC 8707) for CI | Without a SYSTEM write path the whole VERIFIED tier is theoretical, and DoD `tier_gates_verified` can never pass. |
| B3 | P1 | Trust level derived from caller-supplied `source_type` (`file_read` → REPOSITORY, `command_output` → SYSTEM) | `evidence_ledger/domain.py`, test `TrustAndTaxonomy` | Derive trust from *identity* (hook identity → source_type must match what the hook observed); let `fact_writer` sign the payload with the hook token and have the server set `source_type` from the tool event kind | A caller choosing its own trust level is the exact flaw §5.8 says v3 fixed for `trust_level`; it moved one field left. |
| B4 | P1 | stdio only; no streamable HTTP; token via env var; design doc assumes sessions/`Mcp-Session-Id` (removed in MCP 2026-07-28); no tool annotations (`readOnlyHint`, `destructiveHint`), no `outputSchema`, no `ttlMs` on list results | `__main__.py`, `mcp_compat.py`, `reference/mcp-server-design.md` | Upgrade SDK target to 2026-07-28; annotate every tool; add structured outputs; HTTP transport for CI/SYSTEM | Clients use annotations to decide confirmation prompts — a `record_*` tool without `destructiveHint:false`/`readOnlyHint` gets the wrong UX; structured output is what lets hooks validate responses. |
| B5 | P1 | Module `Protocol` promises role-scoped tool registration; `register_tools` registers everything for every caller; scoping is left to client config | `app.py`, `modules/*/tools.py` | Server-side: `register_tools(server, ledger, identity)` already receives identity — filter by `ROLE_TOOLS` from `role-tool-permissions.md` (make that file JSON and the single source) | Client-side tool lists are REPOSITORY-trust config; server-side filtering is the only one an agent cannot edit. |
| B6 | P1 | `vocab.AGENT_ROLES` lacks `product-planner` and `test-engineer`; a credential for those roles fails validation | `kernel/vocab.py:19-21` | Add; generate vocab from `skills/roles/*/role.yaml` in a test | Two of the v3.1 roles cannot authenticate. |
| B7 | P1 | Lifecycle edge cases (audit, PLAUSIBLE — needs tests): approvals not epoch-scoped (a PLAN_APPROVED survives re-planning); `BLOCKED` from `PLAN_APPROVED`/`INTEGRATED` has no exit; merge while FAILED | `change_management/domain.py:22-45`, `api.py:159-193` | Add `approval_epoch` incremented on any `tasks[]`/scope change; define BLOCKED exits for every state; property-test the transition table | Approval of plan N must not authorize plan N+1 — that is the core of ITIL normal-change authorization. |
| B8 | P2 | `work_planning` duplicates AC hash and schema logic from planning-gates (see S2) | `domain.py:46` | Import shared lib | — |
| B9 | P2 | Credentials: no expiry, no rotation, no revocation list | `scripts/adlc_credentials.py` | `expires_at`, `revoke`, SessionStart hook refuses expired | CISA 2026: short-lived credentials per agent. |

### C. Evidence Ledger & grounding (`skills/core/**`, `skills/grounding/**`)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| C1 | P1 | `ledger-entry.schema.json` drifted from `store.py`; neither is tested against the other | Generate the JSON schema from the store's column map in a test | One source. |
| C2 | P1 | Content commitment + 90-day retention design is sound, but `purge` leaves no `purged_at` marker row and `verify` after purge is undocumented | Append a `PURGE` system entry naming the range; document verify semantics | Auditors ask "what was deleted and when". |
| C3 | P2 | evidence-gate honestly says it cannot enforce prose sourcing — good — but `record_handoff` does not validate `source` on FACT / `input_references` on INFERENCE (listed as a future enforcement row) | Implement in `record_handoff`/`record_evidence` (cheap: fields already exist) | Turns the most-cited grounding rule from guideline to structural. |
| C4 | P1 | qa-derive can `query_evidence` and read developer FACT rows that contain source code (via A1) — code-blindness bypass | Apply role read-deny globs to `source_path` server-side; omit `content` for roles whose deny list matches | Blindness that holds at file tools and fails at the ledger is not blindness. |
| C5 | P2 | `ambiguity-escalation` "never ask empty-handed" is excellent and consistently applied in preflight; keep. | — | — |

### D. Product planning (`skills/product-planning/**`, `planning-gates/**`)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| D1 | P0 | AC hash divergence (S2) | Shared `ac_hash` | — |
| D2 | P0 | Evidence exporter / status recorder / tracker projection missing (S5) | Implement | — |
| D3 | P1 | `examples/plans/evidence/evidence.json` is hand-written "SYSTEM" evidence; the README says "in production this file is produced by the CI job" — which does not exist | Generate it from the real exporter in a test; keep the hand-written one only as a fixture labelled as such | The example currently teaches users to author evidence. |
| D4 | P1 | `readiness_gate` ignores SYSTEM records for JUDGMENT items ✔ (tested) — but accepts any `actor_type: AGENT` + `role` string from the evidence file; identity is only as good as the exporter | Exporter must emit server-derived identity; add `entry_id` cross-check against the ledger chain | Evidence files are the attack surface once agents can write `.adlc/`. |
| D5 | P2 | DoR/DoD policy YAML uses a custom `minyaml.py`; every policy edit risks a parser gap | Keep stdlib-only (correct for CI portability) but add a round-trip test that `minyaml` ≡ PyYAML on the three policy files | Cheap insurance. |
| D6 | P2 | `milestone-planner` exit criteria `check: STRUCTURAL` have no evaluator | Add `milestone_gate.py` or mark as informational | — |
| D7 | — | Story types with tier floors, `touches` driving conditional items, size as predicted diff (not points), AC freeze — **keep**; this is the best planning model I have seen in an agent platform | — | Scales process to risk via `applies`, not separate checklists; calibration signal built in. |

### E. Test engineering (`skills/testing/**`, `test-integrity/**`, `test-engineer` role)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| E1 | P0 | Red/green, flake gate, mutation are stubs (A5) | Ship | — |
| E2 | P1 | `test_integrity_guard.py --overrides` reads a file in `head/` (S3) | Overrides from ledger only | — |
| E3 | P1 | Impact-plan vs diff comparison is described in `suite-authoring` and the schema; no CI job exists | `impact_plan_check.py` | Undeclared test files are the scope-creep vector for test-engineer. |
| E4 | P1 | Stack skills are ~30% boilerplate (identical Preflight paragraphs copied into 20+ files) | Move the shared Preflight text to `stage-preflight/reference/standard-preflight.md`; each skill keeps only its deltas | Claude Code shows ~1,536 chars of description; SKILL.md bodies load on invocation — 30% duplicate text is pure token cost and drifts (already differs in wording across files). |
| E5 | P2 | `flaky-detector.py` is solid; `test_asset_catalog.py` step regexes are reasonable; `boundary_values.py` is excellent (unspecified ≠ invalid) — **keep all three** | — | Deterministic, seeded, stdlib. |
| E6 | P2 | `stack_fingerprint.py` misses: `deno.json`, `bun.lock`, `Podfile`, `MODULE.bazel`, `Directory.Packages.props`, `libs.versions.toml`, `pnpm-workspace.yaml`, `uv.lock`, Maestro `config.yaml`; no vendored/generated exclusion beyond dir names; no monorepo workspace walk | Widen to Renovate/Dependabot parity; add workspace walker (`workspaces`, `pnpm-workspace.yaml`, `settings.gradle` includes, `.sln`) | Research: these are the top-5 detection misses in 2026 tooling; a wrong fingerprint mis-routes every stack skill. |
| E7 | — | `ai-agent-testing` catalogs (ASI01/02/03/06/08/09) are well designed with explicit enforcement points and "model declined ≠ pass" — **keep**; add a harness | Build a minimal harness (direct MCP calls + hook invocation) that runs AAT-ASI03-001…011 and AAT-ASI02-006/007 in CI | These are the tests that prove the platform's own claims; without them §4 S1 cannot be closed. |

### F. Workflow / stages (`skills/workflow/**`)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| F1 | P0 | Single-repo planning role resolves MISSING (S5) | Default `planning` = app repo when `plans/` exists or when single-repo | ADR 0004 §4 says so; the code does not. |
| F2 | P1 | `stage_preflight.py --existing-repo no` and `--mode characterization` are agent-controllable switches that relax inputs | Derive from resolver/story; log any override as RISK | Preflight is advisory to the agent but its JSON is recorded as evidence — make the recorded form non-gameable. |
| F3 | P1 | `ingest_documents.py` prints JSON with non-ASCII (UnicodeEncodeError on Windows cp1252 consoles — audit, PLAUSIBLE) | `sys.stdout.reconfigure(encoding="utf-8")` in every script `main()` | Pilot users are on Windows (this repo is). |
| F4 | P1 | Conductor "never skip a gate" relies on the agent calling the gates; only CI enforces | State it (already does, honestly) and add the `checkpoint.json` schema validation to CI so a run that skipped a gate cannot be resumed | — |
| F5 | P2 | `stages.yaml` is JSON-in-YAML (fine for `minyaml`) but `check_skill_contracts.py` and `stages.yaml` vocabularies are not cross-checked | Test | — |
| F6 | — | `requirements-ingestion` (section hashes, source register, traceability matrix with COVERED/PARTIAL/NOT_REQUIREMENT/QUESTION/OUT_OF_SCOPE) is the right design for the primary entry — **keep** | — | Section-hash diffing is what makes re-ingestion safe. |

### G. Stack-agnostic "decide on the fly" (user's explicit goal)

The user's goal: *the platform must work for any tech stack and use AI to decide on the fly what fits the component by looking at its files.* Current design is right in principle — deterministic fingerprint → routing binds stack skills → over-include on doubt. Gaps:

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| G1 | P1 | Five independent manifest/stack parsers (S2) | One `repo-facts` engine producing `stack.json`, `conventions.json`, `workspace.json`, `system-map.json` with per-package granularity | Nx/Renovate model: one project graph, many consumers. |
| G2 | P1 | No per-package stack in monorepos; root toolchain assumed | Workspace walker; `stack.json.packages[]` | A Flutter app and a Node BFF in one repo get one fingerprint today. |
| G3 | P1 | Routing is described (`scope-matrix.md`) but no router script exists; "mandatory loaded by policy" is prose | `route.py`: stack.json + paths + story type → binding set JSON; `paths:` frontmatter on stack skills so Claude Code scopes them natively | Research: LLM-selected skills are advisory; mandatory bindings must be computed. Claude Code's `paths:` field does this for free. |
| G4 | P2 | For structure beyond regex (symbols, cross-file refs), adopt tree-sitter as an *optional* second pass; never SCIP as a precondition | Document in `repo-facts` | Fast first pass stays stdlib; precision where a build exists. |
| G5 | P2 | Multi-repo system ingestion (relationships between repos) is planned, not built; `scan-api-calls.py` cross-match is the seed | Build `system-map.json` from OpenAPI/AsyncAPI/proto + env/host literals + Backstage `catalog-info.yaml` if present; optional OTel servicegraph import | Static alone misses queues/flags; the design already says OBSERVED outranks STATIC. |

### H. Roles & tool compatibility (`skills/roles/**`, `dist/**`, `docs/tool-compatibility.md`)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| H1 | P0 | Copilot agents carry denials as prose (S6) | Mark as instructed; route blind/reviewer roles to Claude Code or sandbox | — |
| H2 | P1 | Claude subagents inherit `permissions.deny` from managed/user settings ✔ but `settings.roles.json` is a *project* file — an agent-writable path unless managed | Generate role denies into the managed template, keyed by subagent name, not into project settings | Project settings are REPOSITORY trust. |
| H3 | P1 | Generated `.claude/agents/*.md` use `tools:` with `mcp__adlc__*` names — fine — but lack `permissionMode`, `maxTurns`, `disallowedTools`, `memory`, `isolation: worktree`; Copilot `.agent.md` uses `tools: ["read","search","edit", ...]` which should be re-verified against the current field reference; `handoffs` correctly avoided | Regenerate from current vendor schemas; add `maxTurns` (the 3-attempt cap finally gets an enforcement point) | `maxTurns` is the only vendor-native iteration cap. |
| H4 | P1 | `tool-compatibility.md` cites hook stdin shapes and AGENTS.md precedence correctly but predates: PreToolUse `hookSpecificOutput.permissionDecision` (incl. `defer`), hook fail-open, Copilot cloud agent `ask→deny`/bash-only, MCP 2026-07-28 | Refresh; add a "spec currency" CI check that fails when the pinned doc version is older than N days | Drift here silently breaks enforcement. |
| H5 | — | Role generator (one `role.yaml` → both vendors, `$ref` to control-file list, scope section auto-generated) — **keep** | — | Hand-maintaining two copies drifts; this is the right pattern. |

### I. Skills as prompts (prompt-engineering review)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| I1 | P1 | Descriptions are 300–600 chars with trigger phrases buried at the end; Claude Code truncates listings at ~1% of context and "the first ~100 characters matter most" | Rewrite every `description` as *what + when* in ≤160 chars, triggers first; move the rest to `when_to_use` | Under-triggering is the #1 skill failure mode (vendor guidance). |
| I2 | P1 | SKILL.md bodies routinely 150–250 lines with reference material inline (e.g. `suite-authoring`, `architecture-package`, `test-data-synthesis`) | Enforce ADR 0006's 500-line budget *and* a 120-line soft target; push tables to `reference/` | Progressive disclosure is the whole point of the skill format. |
| I3 | P2 | Honest enforcement labelling ("guideline only — no enforcement point yet") is consistently present — **keep**; it is the single most trust-building convention in the repo | Make the label machine-checkable (an `## Enforcement` section must contain one of three fixed phrases) | Lets the enforcement-map check (S1) be automated. |
| I4 | P2 | Several skills still carry `<!-- reconstructed: v2 source not provided; review -->` | Review and remove or keep with a date | A reader cannot tell what is settled. |
| I5 | P2 | Positive-instruction style, "why" explanations, no ALL-CAPS — good; `prompt-engineer/reference/prompt-patterns.md` is itself a correct 2026 pattern list — **keep** | — | — |
| I6 | P1 | **83 skills is too many for the skill mechanism itself.** Claude Code puts every `name + description` into context at level 1, capped at ~1% of the window; 83 descriptions of 300–600 chars ≈ 8–10k tokens, so the listing degrades to names only and skills under-trigger. Copilot matches on the same descriptions. Four web-UI and six mobile skills overlap on trigger (the model is asked to choose what `stack.json` already knows). ~20 testing skills duplicate the same Preflight paragraph. `governance/*`, `core/*`, `grounding/*`, `binding-vs-advisory`, `definition-of-ready/done` are always-on rules or explanations of config files, not model-invoked capabilities. | Consolidate **83 → 31** per Appendix B: one skill per capability/surface; stack variants become `reference/` files keyed by `stack.json` with `paths:` scoping; always-on rules move to `.claude/rules/*.md` and roles' `skills:` lists; config-explainer skills become reference docs under `enforcement/`/`docs/`. No content deleted — everything moves one disclosure level down. Update `scope-matrix.md`, `stages.yaml → skills[]`, `role.yaml → required_skills`, generator and `check_skill_contracts.py` atomically. | Vendor guidance (Anthropic Agent Skills, Claude Code `paths:`/`rules/`, "more tools don't lead to better outcomes") and routing research both say selection accuracy falls with catalog size and that the first ~100 chars of a description decide triggering. 31 × ≤160 chars ≈ 1.2k tokens fits the budget with room. The stack-agnostic goal is served *better*: "which framework" becomes a deterministic lookup inside one skill instead of a routing choice among ten. Counter-argument — roles preload skills via `skills:` so count doesn't matter — holds for role work only, not user-invoked skills, and does not fix boilerplate drift. Do it **before** the P0 enforcement wiring, because the wiring references skill paths. |

### J. Self-improvement (`skills/self-improvement/**`, ADR 0006)

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| J1 | P1 | Incident/lesson JSON schemas ≠ `record_incident`/`record_lesson` validation (S2) | One schema, loaded by both | — |
| J2 | P1 | `lesson_lint.py`, `sanitize_check.py`, `build_blocklist.py` exist; `sanitize_check` reuse of `fixture_pii_scan` is by import path that assumes repo layout; no test that a glossary term is blocked | Tests over `examples/plans` glossary | Fail-closed sanitization is the control; prove it. |
| J3 | — | Design (signal + pointers, lesson per cluster, synthetic red/green, gates over prose, pruning) — **keep**; it is strictly better than the user's original "short notes only" and the ADR explains why | — | — |

### K. Governance, supply chain, measurement

| ID | Sev | Finding | Recommendation | Why best |
|---|---|---|---|---|
| K1 | P1 | Platform artifacts (skills, `dist/`, MCP server) are unsigned; no SBOM; no SLSA provenance; `strictKnownMarketplaces` not set | Package `skills/<group>` as plugins; cosign keyless + in-toto attestations in release CI; SLSA L2 | OWASP ASI04; GitGuardian 2026 — the platform is itself a supply-chain input to every repo it touches. |
| K2 | P1 | No AI-authorship trailer policy; ledger `model_id` exists but commits carry nothing | Require `Co-Authored-By:`/`Assisted-by:` trailer + `ADLC-Run:` trailer linking to the run id; CI check | SOC 2 SoD: human author accountable, AI disclosed; links commit → ledger. |
| K3 | P1 | `pilot-measurement.md` is a blank template; no script computes any of the 5 baseline or the planning/test health metrics | `metrics_export.py` over forge API + ledger; wire DORA four keys + instability + PR size/review-wait/no-review-merge | DORA 2025: measurement is capability #1 of 7; without a baseline the pilot cannot be judged. |
| K4 | P2 | Autonomy gating thresholds exist; no computation of verification strength | `verification_strength.py` from flake rate + mutation + coverage | — |
| K5 | P2 | No AI inventory/impact-assessment artifact (NIST AI 600-1 MAP-1, ISO 42001 6.1.4, EU AI Act Art. 4 literacy) | `docs/governance/ai-inventory.md` listing each role, its tools, data classes, Rule-of-Two legs | Required by every AI governance framework; one page. |

### L. Documentation integrity

| ID | Sev | Finding | Recommendation |
|---|---|---|---|
| L1 | P1 | `enforcement-map.md` overclaims (S1) | Three-column rewrite + CI check |
| L2 | P1 | `README.md` build-sequence checkboxes mark 1, 3, 4, 6, 7, 9, 10 done while 4 (ledger) has no SYSTEM path and 8a/9a are "in progress" with stubs | Rewrite status from the v4 plan §9 |
| L3 | P2 | `reference/mcp-server-design.md` claims a Bash deny on `ledger_cli` that does not exist in any template | Remove or add |
| L4 | P2 | Plan v3.1 §6 still says "Server 1/2/3" in places; ADR 0001 says modules | v4 plan fixes |

---

## 6. Things I considered recommending and rejected (so they are not re-litigated)

| Idea | Why rejected |
|---|---|
| Split the MCP server into three services now | No pilot evidence of scale need; triples auth surface; ADR 0001's extractability is already enforced by the boundary test. |
| Replace `minyaml.py`/stdlib scripts with PyYAML/pydantic | Breaks the "CI gate works anywhere with Python 3.10" property that makes the gates deployable without a venv. Keep stdlib; add parity tests. |
| Make `.adlc/**` a control file | Would block agents from running discovery scripts legitimately. Hash-anchor outputs in the ledger instead. |
| Full shell-command parser in `control_file_guard.py` | Arms race; vendor sandbox is the right primitive. |
| LLM-based stack detection ("just read the repo") | Non-deterministic, costs tokens per run, un-cacheable; contradicts the FACT model. Widen tables instead. |
| Story points / velocity in planning | Agent estimates are uncalibrated; predicted-diff size with calibration is strictly more useful (already the design). |
| Letting agents mark characterization tests as AC coverage after review | Would reopen "code is the oracle". Graduation path exists: add AC later. |
| Native Copilot handoffs | Not supported on cloud agent; MCP `record_handoff` is already the durable path. |

---

## 7. What "best" looks like after remediation (target state in one paragraph)

One stdlib `repo-facts` engine produces per-package stack, conventions, workspace and system-map facts, hash-anchored in a per-workspace ledger that CI can write to as SYSTEM through a CLI/HTTP path. Every enforcement row names a test that exercises the block; rows without one are labelled guideline. Blind roles run only where blindness is enforceable (Claude Code with managed denies; sandboxed Bash or no Bash); Copilot runs the roles whose controls hold there. Red/green, flake and diff-scoped mutation gates run in CI from the stack fingerprint's runner adapters. The documents → ARCHITECTURE → PLAN → READY → DONE path runs end to end on `examples/plans` in CI with real exported evidence. Platform releases are signed with provenance; commits carry AI-authorship and run-id trailers; a metrics exporter produces the DORA/planning/test health tables weekly. None of that changes the architecture; all of it is what the architecture already promises.

---

## 8. Prioritized remediation plan

Effort: S ≤ 1 day, M ≤ 1 week, L ≤ 3 weeks (one engineer).

### P0 — before any pilot touches a real repo
| # | Item | Findings | Effort |
|---|---|---|---|
| 1 | Shared `ac_hash` + cross-check test on `examples/plans` | D1, S2 | S |
| 2 | `ledger_cli.py export-planning-evidence`, `record-planning-status`, `ingest-ac-coverage`, `record-gate` (SYSTEM write path) + e2e test | D2, B2, S5 | M |
| 3 | Single-repo `planning` role default | F1 | S |
| 4 | `fact_writer` redaction: digest-only for file reads, secret/PII regex, `source_path`; server-side read-deny on `query_evidence` | A1, C4 | M |
| 5 | Split control-file categories platform vs target | A2 | S |
| 6 | Per-workspace DB + `workspace_id` + required `change_set_id`/`story_id` + response envelope | B1 | M |
| 7 | `ADLC_REQUIRE_HOOK_TOKEN=1` default; `.adlc/catalog` hash-anchoring; overrides from ledger only | S3, S4, E2 | M |
| 8 | Enforcement map → three columns; README status rewrite; remove nonexistent-deny claims | S1, L1–L3 | S |
| 9 | Copilot: label denials as instructed; route blind roles to Claude Code/sandbox; refresh `tool-compatibility.md` | H1, H4, S6 | S |

### P1 — before enterprise adoption
| # | Item | Findings | Effort |
|---|---|---|---|
| 10 | `red_green_check.py`, `flake_gate.py`, mutation adapters + DoD `mutation` gate | A5, E1 | L |
| 11 | `repo-facts` engine: manifest tables to Renovate parity, workspace walker, per-package stack; four scanners import it | G1, G2, E6, S2 | L |
| 12 | `route.py` + `paths:` frontmatter on stack skills | G3 | M |
| 13 | Server-side role tool filtering; `AGENT_ROLES` from role.yaml; credential expiry | B5, B6, B9 | M |
| 14 | MCP 2026-07-28: annotations, outputSchema, HTTP transport w/ OAuth 2.1 + RFC 8707 | B4 | L |
| 15 | Approval epochs, BLOCKED exits, property tests on lifecycle | B7 | M |
| 16 | Managed-settings key verification + missing keys (`allowManagedMcpServersOnly`, `strictKnownMarketplaces`, `disableSkillShellExecution`) + deployed-vs-template check | A3, A6 | S |
| 17 | Wire `dependency-decision-check` and `impact_plan_check.py` into gates | A4, E3 | S |
| 18 | AI-agent-testing harness running ASI03/ASI02 catalogs in CI | E7 | M |
| 19 | Signed releases (cosign + in-toto, SLSA L2), plugin packaging, marketplace pinning | K1 | M |
| 20 | Commit trailer policy + CI check | K2 | S |
| 21 | `metrics_export.py` (DORA + planning + test health) and `verification_strength.py` | K3, K4 | M |
| 22 | Description rewrite (≤160 chars, triggers first); shared preflight reference; size budget check | I1, I2, E4 | M |
| 22a | **Skill catalog consolidation 83 → 31** (Appendix B manifest), done as one reviewed PR *before* items 10–18 so enforcement wiring targets the final paths | I6 | M |
| 23 | Schema unification: ledger entry, incident, lesson; sanitize tests | C1, J1, J2 | S |
| 24 | AI inventory / impact assessment page | K5 | S |

### P2 — quality
Items A7, A8, C2, C3, D5, D6, F3–F5, G4, G5, I4, L4.

---

## 9. Appendix A — finding index

S1–S6 systemic · A1–A8 enforcement · B1–B9 MCP · C1–C5 ledger/grounding · D1–D7 planning · E1–E7 testing · F1–F6 workflow · G1–G5 stack-agnostic · H1–H5 roles/compat · I1–I6 prompts/catalog · J1–J3 self-improvement · K1–K5 governance · L1–L4 docs.

Confirmed by reading: all except B7 (lifecycle edge cases) and F3 (Windows encoding), which are audit-reported and marked PLAUSIBLE pending a test.

---

## 10. Appendix B — skill catalog consolidation (83 → 31)

### B.1 Rules applied
1. **One skill = one capability with one trigger.** If two skills are only ever chosen by the same signal (the repo's stack), they are one skill with a reference per variant.
2. **Always-on rules are not skills.** They go to `.claude/rules/adlc-*.md` (Claude Code, `paths:`-scoped where useful) and to each role's `skills:`/system prompt via the generator; Copilot gets them through `.github/instructions/*.instructions.md` with `applyTo`.
3. **Config explainers are not skills.** A skill whose body explains a JSON/YAML file (DoR, DoD, control-file policy) becomes a `reference/` file of the skill that *uses* the config.
4. **Human/CI-run procedures are not agent skills.** They become `docs/` + scripts.
5. **Nothing is deleted.** Every `reference/`, `scripts/`, `tests/`, `templates/`, `schemas/` directory moves intact. `SKILL.md` bodies that stop being skills are renamed `reference/<old-name>.md` under their new owner.
6. `description` ≤160 chars, *what + when*, triggers first; `when_to_use` carries the rest; body ≤120 lines soft / 500 hard; one shared `preflight` reference replaces the copied paragraphs.

### B.2 Target catalog (31 skills)

| # | New skill | Scope | `paths:` |
|---|---|---|---|
| 1 | `grounding/adlc-grounding` | evidence rules, ask-vs-assume, trust boundaries, failure modes, review format, ledger & fact classes (all as references); always-on via rules files | — |
| 2 | `self-improvement/self-improvement` | failure capture + improvement review | — |
| 3 | `routing/routing` | `route.py`, scope matrix, precedence, token budget (refs) | — |
| 4 | `change-management/change-set` | lifecycle, snapshot/staleness, tasks, parallel execution, resumability (refs) | — |
| 5 | `change-management/risk-tiering` | script-backed | — |
| 6 | `change-management/dependency-discovery` | script-backed | — |
| 7 | `contracts/contracts` | registry, can-i-deploy, drift (procedures) | `**/openapi*`, `**/*.proto`, `**/*.avsc`, `**/asyncapi*`, `**/*.pact.json` |
| 8 | `product-planning/requirement-intake` | | `plans/requirements/**`, `plans/intake/**` |
| 9 | `product-planning/story-writer` | AC standard, story schema, story types (refs) | `plans/stories/**` |
| 10 | `product-planning/story-refinement` | three amigos + DoR self-check (readiness-gate ref) | `plans/stories/**` |
| 11 | `product-planning/plan-decomposition` | epics, milestones, dependency mapping | `plans/epics/**`, `plans/milestones/**` |
| 12 | `workflow/adlc` | the conductor (`/adlc`) | — |
| 13 | `workflow/requirements-ingestion` | | — |
| 14 | `workflow/preflight` | workspace resolution + stage preflight + brownfield adoption; the single shared Preflight reference | — |
| 15 | `engineering-design/architecture` | package, system design, data-store & messaging matrices, scale readiness, templates (refs) | `architecture/**`, `docs/adr/**` |
| 16 | `engineering-design/project-conventions` | script-backed | — |
| 17 | `engineering-design/code-design-review` | SOLID, anti-patterns, perf (refs); DoD completion-gate ref lives here (read at REVIEW) | — |
| 18 | `ai-integration/llm-integration` | LLM architecture + RAG (refs) | — |
| 19 | `ai-integration/prompt-engineer` | | `**/prompts/**`, `**/*.prompt.*`, `skills/**/SKILL.md` |
| 20 | `testing/test-strategy` | strategy + pyramid | — |
| 21 | `testing/test-repo-discovery` | script-backed | — |
| 22 | `testing/test-design` | YAML design + Gherkin authoring (format chosen from `stack.json.bdd`) | `plans/test-designs/**`, `**/*.feature` |
| 23 | `testing/test-data` | synthesis + environment data lifecycle | `**/fixtures/**`, `**/factories/**`, `**/testdata/**` |
| 24 | `testing/suite-authoring` | modes A/B/C, impact plan, determinism, BDD step binding (ref) | test globs |
| 25 | `testing/web-ui-testing` | refs: `playwright.md`, `selenium.md`, `visual-regression.md`, `headless-vs-headed.md`, `selectors.md`, `flaky-patterns.md` | `**/e2e/**`, `**/*.spec.*`, `**/*.cy.*`, `**/playwright.config.*` |
| 26 | `testing/mobile-testing` | refs: `flutter.md`, `detox.md`, `appium.md`, `xcuitest.md`, `espresso.md`, `device-matrix.md` | `**/*.dart`, `**/*.swift`, `**/*.kt`, `**/android/**`, `**/ios/**`, `**/.detoxrc*` |
| 27 | `testing/api-contract-testing` | refs: `pact.md`, `newman.md`, `schema-validation.md` | contract globs |
| 28 | `testing/performance-testing` | refs: `load-testing.md` (k6/JMeter), `baseline-tracker.md`, `bottleneck-analysis.md` | `**/perf/**`, `**/load/**`, `**/*.jmx` |
| 29 | `testing/test-maintenance` | refs: `flaky-intelligence.md` (+script), `self-healing-locators.md` | test globs |
| 30 | `testing/security-scanning` | refs: `sast.md`, `sca.md`, `secrets.md`, `deployment-verification.md` | — |
| 31 | `testing/agent-security-tests` | refs: four ASI catalogs + `asi-mapping.md` | — |

Not skills any more: `governance/*` (→ `enforcement/governance/` + `docs/governance/`), `workflow/repo-bootstrap` (→ `docs/repo-bootstrap.md` + script), `product-planning/definition-of-ready|done` (→ refs), `skill-routing/binding-vs-advisory` (→ rules file), `core/*` (→ grounding refs).

### B.3 Move manifest (old → new)

```
# grounding + core → one skill + rules files
skills/grounding/evidence-gate/SKILL.md                 → skills/grounding/adlc-grounding/reference/evidence-gate.md      (+ .claude/rules/adlc-evidence.md)
skills/grounding/ambiguity-escalation/SKILL.md          → skills/grounding/adlc-grounding/reference/ambiguity-escalation.md (+ rules)
skills/grounding/trust-boundaries/SKILL.md              → skills/grounding/adlc-grounding/reference/trust-boundaries.md     (+ rules)
skills/grounding/agent-failure-modes/SKILL.md           → skills/grounding/adlc-grounding/reference/agent-failure-modes.md
skills/grounding/human-review-format/SKILL.md           → skills/grounding/adlc-grounding/reference/human-review-format.md
skills/grounding/*/reference/*                          → skills/grounding/adlc-grounding/reference/   (flatten, keep names)
skills/core/evidence-ledger/SKILL.md                    → skills/grounding/adlc-grounding/reference/evidence-ledger.md
skills/core/evidence-ledger/reference/*                 → skills/grounding/adlc-grounding/reference/
skills/core/fact-classification/SKILL.md                → skills/grounding/adlc-grounding/reference/fact-classification.md
skills/core/fact-classification/reference/*             → skills/grounding/adlc-grounding/reference/
skills/core/schemas/ledger-entry.schema.json            → skills/grounding/adlc-grounding/schemas/   (generated from store in a test)
NEW skills/grounding/adlc-grounding/SKILL.md            (≤120 lines; "which reference when" table)

# self-improvement → one skill
skills/self-improvement/failure-capture/SKILL.md        → skills/self-improvement/self-improvement/SKILL.md §Capture
skills/self-improvement/improvement-review/SKILL.md     → skills/self-improvement/self-improvement/SKILL.md §Review
skills/self-improvement/*/reference/*                   → skills/self-improvement/self-improvement/reference/ (scripts, schemas, taxonomy unchanged)

# governance → not skills
skills/governance/default-permissions/reference/*       → skills/enforcement/governance/   (control-file-paths.json stays the single source; generator paths updated)
skills/governance/default-permissions/SKILL.md          → docs/governance/default-permissions.md
skills/governance/autonomy-gating/**                    → docs/governance/autonomy-gating.md + verification-strength.md
skills/governance/permission-scoping/SKILL.md           → docs/governance/permission-scoping.md (+ ai-inventory.md)
skills/governance/policy-drift-check/SKILL.md           → docs/governance/policy-drift-check.md (+ verify_deployed.py under enforcement/)

# skill-routing → one skill
skills/skill-routing/skill-router/SKILL.md              → skills/routing/routing/SKILL.md
skills/skill-routing/skill-router/reference/*           → skills/routing/routing/reference/
skills/skill-routing/binding-vs-advisory/SKILL.md       → .claude/rules/adlc-precedence.md  (+ reference copy)
skills/skill-routing/binding-vs-advisory/reference/*    → skills/routing/routing/reference/
skills/skill-routing/token-budget-optimizer/**          → skills/routing/routing/reference/token-budget/
NEW skills/routing/routing/scripts/route.py

# change-management 5 → 3
skills/change-management/snapshot/SKILL.md              → skills/change-management/change-set/reference/snapshot.md
skills/change-management/snapshot/reference/*           → skills/change-management/change-set/reference/
skills/change-management/parallel-execution/SKILL.md    → skills/change-management/change-set/reference/parallel-execution.md
skills/change-management/parallel-execution/reference/* → skills/change-management/change-set/reference/
skills/change-management/{change-set,risk-tiering,dependency-discovery}/**   unchanged

# contracts 3 → 1
skills/contracts/contract-registry/SKILL.md             → skills/contracts/contracts/SKILL.md §Register
skills/contracts/compatibility-check/SKILL.md           → skills/contracts/contracts/SKILL.md §Can-I-Deploy
skills/contracts/drift-detection/SKILL.md               → skills/contracts/contracts/SKILL.md §Drift
skills/contracts/*/reference/*, scripts/*, tests/*      → skills/contracts/contracts/{reference,scripts,tests}/

# product-planning 8 → 4
skills/product-planning/definition-of-ready/**          → skills/product-planning/story-refinement/reference/definition-of-ready.md (+ readiness-gate.md)
skills/product-planning/definition-of-done/**           → skills/engineering-design/code-design-review/reference/definition-of-done.md (+ completion-gate.md)
skills/product-planning/epic-decomposer/**              → skills/product-planning/plan-decomposition/ (SKILL §Epics; refs kept)
skills/product-planning/milestone-planner/**            → skills/product-planning/plan-decomposition/ (SKILL §Milestones; refs kept)
skills/product-planning/dependency-mapper/SKILL.md      → skills/product-planning/plan-decomposition/reference/dependency-mapping.md
skills/product-planning/{requirement-intake,story-writer,story-refinement}/**  unchanged
skills/product-planning/{policies,schemas}/             unchanged (control files)

# workflow 6 → 3
skills/workflow/adlc-conductor/**                       → skills/workflow/adlc/
skills/workflow/workspace-resolver/**                   → skills/workflow/preflight/ (SKILL §Workspace; script kept)
skills/workflow/stage-preflight/**                      → skills/workflow/preflight/ (SKILL §Inputs; script kept)
skills/workflow/brownfield-adoption/**                  → skills/workflow/preflight/reference/brownfield-adoption.md (+ import_tracker.py)
skills/workflow/repo-bootstrap/SKILL.md                 → docs/repo-bootstrap.md
skills/workflow/repo-bootstrap/scripts/*                → skills/workflow/preflight/scripts/
skills/workflow/{stages.yaml,lib,schemas,requirements-ingestion}  unchanged
NEW skills/workflow/preflight/reference/standard-preflight.md   (the one copy every skill links)

# engineering-design 7 → 3
skills/engineering-design/architecture-package/**       → skills/engineering-design/architecture/ (SKILL body)
skills/engineering-design/system-architect/**           → skills/engineering-design/architecture/reference/system-design.md + reference/{decomposition,scaling}.md + templates/
skills/engineering-design/data-store-selector/**        → skills/engineering-design/architecture/reference/data-store-selection.md + decision-matrix
skills/engineering-design/messaging-selector/**         → skills/engineering-design/architecture/reference/messaging-selection.md + decision-matrix
skills/engineering-design/scale-readiness-reviewer/**   → skills/engineering-design/architecture/reference/scale-readiness.md
skills/engineering-design/code-design-reviewer/**       → skills/engineering-design/code-design-review/
skills/engineering-design/project-conventions/**        unchanged

# ai-integration 3 → 2
skills/ai-integration/rag-pipeline-expert/SKILL.md      → skills/ai-integration/llm-integration/reference/rag-pipeline.md
skills/ai-integration/llm-integration-architect/**      → skills/ai-integration/llm-integration/
skills/ai-integration/prompt-engineer/**                unchanged

# testing 35 → 12
skills/testing/test-architecture/test-strategy/**       → skills/testing/test-strategy/
skills/testing/test-architecture/test-pyramid-advisor/SKILL.md → skills/testing/test-strategy/reference/test-pyramid.md
skills/testing/test-architecture/test-repo-discovery/** → skills/testing/test-repo-discovery/
skills/testing/test-design/test-case-design/**          → skills/testing/test-design/
skills/testing/test-design/bdd-feature-authoring/SKILL.md → skills/testing/test-design/reference/gherkin-authoring.md (+ style guide)
skills/testing/test-data/test-data-synthesis/**         → skills/testing/test-data/
skills/testing/test-maintenance/test-data-management/SKILL.md → skills/testing/test-data/reference/environment-data-lifecycle.md
skills/testing/test-implementation/suite-authoring/**   → skills/testing/suite-authoring/
skills/testing/test-implementation/bdd-step-binding/SKILL.md → skills/testing/suite-authoring/reference/bdd-step-binding.md
skills/testing/web-ui-automation/playwright-expert/SKILL.md   → skills/testing/web-ui-testing/reference/playwright.md
skills/testing/web-ui-automation/playwright-expert/reference/* → skills/testing/web-ui-testing/reference/
skills/testing/web-ui-automation/selenium-expert/SKILL.md     → skills/testing/web-ui-testing/reference/selenium.md
skills/testing/web-ui-automation/visual-regression/SKILL.md   → skills/testing/web-ui-testing/reference/visual-regression.md
skills/testing/web-ui-automation/headless-vs-headed/SKILL.md  → skills/testing/web-ui-testing/reference/headless-vs-headed.md
NEW skills/testing/web-ui-testing/SKILL.md              (lookup table on stack.json.e2e_driver / ui_paradigm)
skills/testing/mobile-automation/flutter-testing/SKILL.md     → skills/testing/mobile-testing/reference/flutter.md
skills/testing/mobile-automation/detox-react-native/SKILL.md  → skills/testing/mobile-testing/reference/detox.md
skills/testing/mobile-automation/appium-expert/SKILL.md       → skills/testing/mobile-testing/reference/appium.md
skills/testing/mobile-automation/ios-xcuitest/SKILL.md        → skills/testing/mobile-testing/reference/xcuitest.md
skills/testing/mobile-automation/android-espresso/SKILL.md    → skills/testing/mobile-testing/reference/espresso.md
skills/testing/mobile-automation/device-matrix/SKILL.md       → skills/testing/mobile-testing/reference/device-matrix.md
NEW skills/testing/mobile-testing/SKILL.md
skills/testing/api-contract-testing/pact-consumer-driven/SKILL.md → skills/testing/api-contract-testing/reference/pact.md
skills/testing/api-contract-testing/postman-newman/SKILL.md       → skills/testing/api-contract-testing/reference/newman.md
skills/testing/api-contract-testing/schema-validation/SKILL.md    → skills/testing/api-contract-testing/reference/schema-validation.md
NEW skills/testing/api-contract-testing/SKILL.md
skills/testing/performance-testing/load-testing-expert/**     → skills/testing/performance-testing/reference/load-testing.md + k6/jmeter refs
skills/testing/performance-testing/perf-baseline-tracker/SKILL.md → skills/testing/performance-testing/reference/baseline-tracker.md
skills/testing/performance-testing/bottleneck-analysis/SKILL.md   → skills/testing/performance-testing/reference/bottleneck-analysis.md
NEW skills/testing/performance-testing/SKILL.md
skills/testing/test-maintenance/flaky-test-intelligence/**    → skills/testing/test-maintenance/ (SKILL body + scripts)
skills/testing/test-maintenance/self-healing-locators/SKILL.md → skills/testing/test-maintenance/reference/self-healing-locators.md
skills/testing/security-testing/sast-scanner/SKILL.md         → skills/testing/security-scanning/reference/sast.md
skills/testing/security-testing/sca-dependency-audit/SKILL.md → skills/testing/security-scanning/reference/sca.md
skills/testing/security-testing/secret-scanning/SKILL.md      → skills/testing/security-scanning/reference/secrets.md
skills/testing/security-testing/deployment-verification/SKILL.md → skills/testing/security-scanning/reference/deployment-verification.md
NEW skills/testing/security-scanning/SKILL.md
skills/testing/ai-agent-testing/*/SKILL.md              → skills/testing/agent-security-tests/reference/{prompt-injection,tool-misuse,agent-authorization,policy-bypass}.md
skills/testing/ai-agent-testing/reference/asi-mapping.md → skills/testing/agent-security-tests/reference/
NEW skills/testing/agent-security-tests/SKILL.md
```

### B.4 Dependent updates (same PR)
- `skills/routing/routing/reference/scope-matrix.md`: skill paths → new names; stack rows become `web-ui-testing#playwright` style anchors.
- `skills/workflow/stages.yaml → stages.*.skills[]`: new paths.
- `skills/roles/*/role.yaml → required_skills`: new paths (lists shrink to 5–7 per role).
- `skills/roles/scripts/generate_agents.py`: emit `skills:` frontmatter from `required_skills`; emit `.claude/rules/adlc-*.md` and `.github/instructions/adlc-*.instructions.md` from the rules sources.
- `docs/tools/check_skill_contracts.py`: add description-length (≤160) and body-size checks; vocabulary unchanged.
- `docs/authoring-conventions.md`: add the three catalog rules (B.1 #1–#4) and the shared-preflight link requirement.
- `docs/enforcement-map.md`, `README.md` layout block, `control-file-paths.json` (`skills/**` still covers everything; `governance` reference path changes).
- Every intra-skill relative link: run a link checker in CI (new, small).

### B.5 What changes for the user
- `/adlc`, `/requirements-ingestion`, `/story-writer`, `/test-design`, `/suite-authoring` etc. still exist as slash-invocable skills; stack choice is automatic.
- Fewer, sharper descriptions → skills trigger when they should.
- Nothing a reviewer could read before is gone; it is one click further down.
