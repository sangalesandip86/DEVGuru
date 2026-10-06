# Enforcement Map — rule → skill → enforcement status

Plan v4 §5.6. Three categories:

- **Enforced** — an artifact exists and a test exercises the block.
- **Detects** — an artifact reports or flags the condition but nothing blocks on it yet.
- **Guideline** — prose instruction only; no enforcement artifact.

A rule stated in a skill with no Enforced or Detects row here is a guideline the model can
choose to follow, not a guarantee. Keep this table current whenever a rule is added.

MCP paths are relative to `skills/mcp-servers/adlc-mcp/src/adlc_mcp/` (one server, `adlc`;
tools appear as `mcp__adlc__<tool>` in Claude Code).

---

## Enforced (artifact + test exercises the block)

| Rule | Stated in (skill) | Artifact | Test |
|---|---|---|---|
| Ledger is append-only and tamper-evident | `core/evidence-ledger` | `modules/evidence_ledger/store.py` (BEFORE UPDATE/DELETE triggers), `record_correction` is the only mutation path | `tests/evidence_ledger/test_evidence_ledger.py` (tamper, delete, reorder detection) |
| Agent cannot write FACT/VERIFIED/APPROVED via MCP | `core/evidence-ledger`, `grounding/trust-boundaries` | `modules/evidence_ledger/domain.py` (`validate_entry`, `LIFECYCLE_AUTHORITY`) | `tests/evidence_ledger/test_evidence_ledger.py` (identity rejection tests) |
| No agent sets APPROVED / INTEGRATED / RELEASED | `grounding/`, plan §5.5 | `modules/change_management/` (`update_status` rejects agent callers); transitions only via `ingest_forge_event` (SYSTEM) or authenticated human | `tests/change_management/test_change_management.py` |
| Plan files have no status field | `product-planning/story-writer` | `skills/enforcement/ci-checks/planning-gates/plan_lint.py` (`additionalProperties: false`, status/state/ready/done/accepted rejected) | `skills/enforcement/ci-checks/planning-gates/tests/test_planning_gates.py` |
| Story READY only when DoR is met (derived, not set) | `product-planning/definition-of-ready` | `skills/enforcement/ci-checks/planning-gates/readiness_gate.py` | `skills/enforcement/ci-checks/planning-gates/tests/test_planning_gates.py` |
| Story DONE only when DoD is met (derived, not set) | `product-planning/definition-of-done` | `skills/enforcement/ci-checks/planning-gates/completion_gate.py`, `ac_coverage.py` | `skills/enforcement/ci-checks/planning-gates/tests/test_planning_gates.py` |
| AC frozen once READY | `product-planning/story-writer` | `skills/enforcement/ci-checks/planning-gates/plan_lint.py` (AC hash diff; mismatch → REFINING, invalidates qa-derive REVIEWED) | `skills/enforcement/ci-checks/planning-gates/tests/test_planning_gates.py` |
| Risk tier always computable; unknown → HIGH | `change-management/risk-tiering` | `skills/change-management/risk-tiering/scripts/path_tier_lookup.py` | `skills/change-management/risk-tiering/tests/test_path_tier_lookup.py` |
| Control files never agent-writable (Claude Code) | `grounding/trust-boundaries` | `skills/enforcement/managed-settings/templates/claude-code-managed-settings.json` (Edit/Write deny), `skills/enforcement/hooks/control-file-guard/control_file_guard.py` (PreToolUse) | `skills/enforcement/tests/test_enforcement.py` |
| Control-file protection deployed matches template | `governance/policy-drift-check` | `skills/enforcement/ci-checks/control-file-policy-check/check_control_file_policy.py`, `generate_deny_list.py --check` | `skills/enforcement/tests/test_enforcement.py` |
| AGENTS.md has a `@AGENTS.md` CLAUDE.md shim | `docs/tool-compatibility.md` | `skills/enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py` | `skills/enforcement/tests/test_enforcement.py` |
| No fixed sleeps in tests | `testing/web-ui-automation/*`, `testing/mobile-automation/*` | `skills/enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py` | `skills/enforcement/ci-checks/test-integrity/tests/test_pii_and_sleep.py` |
| No PII / production data / secrets in fixtures | `testing/test-data/test-data-synthesis` | `skills/enforcement/ci-checks/test-integrity/fixture_pii_scan.py` | `skills/enforcement/ci-checks/test-integrity/tests/test_pii_and_sleep.py` |
| Test expectations change only when AC changes | `testing/test-implementation/suite-authoring` | `skills/enforcement/ci-checks/test-integrity/test_integrity_guard.py` | `skills/enforcement/ci-checks/test-integrity/tests/test_test_integrity_guard.py` |
| ORG lesson promotion requires human APPROVED | `self-improvement/improvement-review` | `modules/evidence_ledger/api.py` (`_promote_lesson`: agent callers rejected, needs HUMAN APPROVED entry) | `tests/evidence_ledger/test_lessons_and_retention.py` |
| Invalid lifecycle transitions rejected | `change-management/change-set` | `modules/change_management/domain.py` (transition table), `api.py` | `tests/change_management/test_change_management.py` |
| DoR/DoD/story-type policy not agent-weakenable | `product-planning/policies/` | `skills/governance/default-permissions/reference/control-file-paths.json` (`planning-policies`) → managed deny + `control-file-guard` | `skills/enforcement/tests/test_enforcement.py` |
| Agent identity authentic; `trust_level` never caller-supplied | `core/evidence-ledger` | `kernel/identity.py`, `modules/evidence_ledger/domain.py` (server-derived) | `tests/evidence_ledger/test_evidence_ledger.py` |
| FACT entries come from hooks, never model self-report | `core/fact-classification` | `skills/enforcement/hooks/fact-writer-hooks/fact_writer.py` → `ledger_cli.py append-fact` | `skills/enforcement/tests/test_enforcement.py` |
| Checkpoint schema valid; no skipped gates on resume | `workflow/adlc-conductor` | `skills/enforcement/ci-checks/planning-gates/checkpoint_validate.py` | `skills/enforcement/ci-checks/planning-gates/tests/test_checkpoint_validate.py` |
| Per-role tool denies in managed settings (client-side) | `grounding/trust-boundaries` | `skills/enforcement/managed-settings/generate_deny_list.py` (`subagentPermissions`) | `skills/enforcement/tests/test_enforcement.py` (`test_committed_template_is_current`) |
| MCP tool annotations (readOnlyHint/destructiveHint) | `grounding/trust-boundaries` | `skills/mcp-servers/adlc-mcp/src/adlc_mcp/kernel/mcp_compat.py` (`TOOL_ANNOTATIONS`) | `skills/mcp-servers/adlc-mcp/tests/kernel/test_mcp_compat.py` |
| Server-side role tool filtering | `grounding/trust-boundaries` | `skills/mcp-servers/adlc-mcp/src/adlc_mcp/kernel/role_permissions.py`, `app.py` (`FilteredServer`) | `skills/mcp-servers/adlc-mcp/tests/kernel/test_role_permissions.py` |
| Impact-plan vs actual diff comparison | `testing/test-implementation/suite-authoring` | `skills/enforcement/ci-checks/test-integrity/impact_plan_check.py` | `skills/enforcement/ci-checks/test-integrity/tests/test_impact_plan_check.py` |
| Worktree isolation per task | `change-management/change-set` | `skills/roles/scripts/generate_agents.py` (`isolation: worktree` in agent frontmatter) | `skills/roles/scripts/tests/test_generate_agents.py` |
| Spec-currency CI check (tool-compatibility.md ≤90 days) | `governance/policy-drift-check` | `skills/enforcement/ci-checks/spec-currency/check_spec_currency.py` | — |
| Handoff schema validation (source on FACT, input_references on INFERENCE) | `grounding/evidence-gate` | `skills/mcp-servers/adlc-mcp/src/adlc_mcp/modules/change_management/domain.py` (`validate_handoff_payload`) | `tests/change_management/test_change_management.py` (`test_handoff_inference_needs_input_references`, `test_handoff_fact_needs_source`, `test_handoff_refs_and_security_reject`) |
| Ledger schema matches JSON schema (no drift) | `core/evidence-ledger` | `skills/mcp-servers/adlc-mcp/schemas/ledger-entry.schema.json` | `tests/evidence_ledger/test_schema_drift.py` |
| Prompt injection in content/metadata does not override classification (ASI01) | `core/evidence-ledger`, `grounding/trust-boundaries` | `modules/evidence_ledger/domain.py` (server-derived fields), `modules/change_management/domain.py` | `tests/aat/test_asi01_prompt_injection.py` (classification, handoff, SQL, unicode — 10 tests) |
| Iteration cap and non-retryable escalation (ASI06) | `grounding/agent-failure-modes` | `modules/change_management/domain.py` (`FAILURE_POLICY`, `ITERATION_CAP`), `api.py` (`record_task_failure`) | `tests/aat/test_asi06_excessive_agency.py` (cap, escalation, role boundaries — 12 tests) |
| Oversized payloads and rapid writes preserve hash chain (ASI08) | `core/evidence-ledger` | `modules/evidence_ledger/store.py` (hash chain), `modules/change_management/domain.py` | `tests/aat/test_asi08_resource_abuse.py` (payloads, integrity, handoff abuse — 10 tests) |
| Dangerous paths blocked on read AND write (path traversal, credentials, SSH keys) | `grounding/trust-boundaries` | `skills/enforcement/lib/adlc_enforcement.py` (`DANGEROUS_PATH_PATTERNS`, `match_dangerous_path`), `skills/enforcement/hooks/control-file-guard/control_file_guard.py` (read + write blocking) | `skills/enforcement/tests/test_enforcement.py` (`PathTraversalGuardTests` — 5 tests) |
| Event journal append-only with hash-chained tamper detection | `core/evidence-ledger` | `modules/event_journal/store.py` (SHA-256 hash chain, per-run GENESIS_HASH), `modules/event_journal/api.py` (actor identity server-derived) | `tests/test_event_journal.py` (chain tamper, deletion detection, fold, tools — 12 tests) |
| Stage transitions validated against declarative graph | `workflow/stage-preflight` | `modules/stage_engine/store.py` (allowed_next, required_roles, required_outputs, gate checks), `modules/stage_engine/domain.py` (TRANSITION_GRAPH) | `tests/test_stage_engine.py` (18 tests: graph, validation, recording, current stage, tools) |
| Task claims enforce mutual exclusion (UNIQUE constraint) | `change-management/parallel-execution` | `modules/concurrency/store.py` (claim_task: SQLite UNIQUE constraint mutex, stale claim cleanup) | `tests/test_concurrency.py` (6 claim tests: acquire, release, conflict, stale) |
| Parallel coordinator max workers capped at MAX_WORKERS | `change-management/parallel-execution` | `modules/parallel_coordinator/store.py` (always caps `max_workers` to `MAX_WORKERS=8`) | `tests/test_parallel_coordinator.py` (max workers capped test, enforcement test) |

---

## Detects (reports, does not block)

| Rule | Stated in (skill) | Artifact | Notes |
|---|---|---|---|
| Dependency manifest changes need a DECISION | `engineering-design/project-conventions` | `skills/enforcement/ci-checks/dependency-decision-check/check_dependency_decisions.py` | Exists; not wired to any stage exit gate or workflow. Wire to IMPLEMENT/REVIEW gate (v4 §9 item 17). |
| Test integrity override detection | `testing/test-implementation/suite-authoring` | `skills/enforcement/ci-checks/test-integrity/test_integrity_guard.py` (`--overrides`) | Reads overrides from `head/`; an agent could author those overrides. Move to ledger REVIEWED entries (v4 §9 item 7). |
| Convention scan deviations | `engineering-design/project-conventions` | `skills/engineering-design/project-conventions/scripts/convention_scan.py` | Reports deviations against declared standards and golden files. |
| Every control-file change attempt is logged | `governance/default-permissions` | `skills/enforcement/hooks/config-change-logger/config_change_logger.py` | Logs attempts; does not block (the guard hook blocks on Claude Code). |
| Milestone exit criteria evaluation | `workflow/adlc-conductor` | `skills/enforcement/ci-checks/planning-gates/milestone_gate.py` | STRUCTURAL auto-evaluated; JUDGMENT/APPROVAL require human evidence. |
| Skill routing computed from stack + paths + story type | `skill-routing/skill-router` | `skills/skill-routing/skill-router/scripts/route.py` | Mandatory bindings deterministic; LLM skills are advisory only. |
| Stage-preflight override risk logging | `workflow/stage-preflight` | `skills/workflow/stage-preflight/scripts/stage_preflight.py` (`_auto_existing_repo`, `overrides`) | Detects `--existing-repo` and `--mode characterization` overrides. |
| SKILL.md description ≤160 chars, body ≤500 lines | `docs/authoring-conventions.md` | `docs/tools/check_skill_contracts.py` | Reports oversized descriptions and bodies. |
| Deployed managed settings match template | `governance/policy-drift-check` | `skills/enforcement/managed-settings/verify_deployed.py` | Detects missing/different keys between deployed and template. |
| Tool-compatibility doc freshness | `docs/tool-compatibility.md` | `skills/enforcement/ci-checks/spec-currency/check_spec_currency.py` | Fails if verified date is >90 days old; prevents silent spec rot. |
| DORA metrics + planning health export | `governance/autonomy-gating` | `skills/mcp-servers/adlc-mcp/scripts/metrics_export.py` | Reports deployment frequency, lead time, change failure rate. |
| Verification strength (coverage × mutation × stability) | `governance/autonomy-gating` | `skills/governance/autonomy-gating/verification_strength.py` | Weighted harmonic mean; tiers HIGH/MEDIUM/LOW. |
| Enforcement label machine-checkable | `docs/authoring-conventions.md` | `docs/tools/check_skill_contracts.py` | Warns if `## Enforcement` lacks Enforced/Detects/Guideline keyword. |
| AI-authorship commit trailer policy | `governance/` | `skills/enforcement/ci-checks/commit-trailer-check/check_commit_trailers.py` | Flags AI commits missing ADLC-Run trailer; wire to PR CI. |
| Quantitative risk score maps to 4-tier model | `change-management/risk-tiering` | `skills/change-management/risk-tiering/scripts/risk_scorer.py` (sigmoid model, tier boundaries) | Reports tier + score; complements path-based lookup. Tested: `skills/change-management/risk-tiering/tests/test_risk_scorer.py` (23 tests). |
| Deterministic regression suite (golden-case replay) | `testing/deterministic-regression` | `skills/testing/deterministic-regression/scripts/replay_runner.py` (5 check functions, fixture replay) | Model-free golden-case validation. Tested: `skills/testing/deterministic-regression/tests/test_replay_runner.py` (7 tests) + 4 golden cases. |
| BM25 similar-task search | `core/evidence-ledger` | `skills/mcp-servers/adlc-mcp/src/adlc_mcp/modules/evidence_ledger/bm25.py` | Ranks historical tasks by relevance. Tested: `skills/mcp-servers/adlc-mcp/tests/test_bm25.py` (14 tests). |
| Lesson relevance ranking (file + text overlap) | `self-improvement` | `skills/self-improvement/scripts/lesson_ranker.py` (Jaccard + BM25, max 8) | Ranks lessons for context assembly. Tested: `skills/self-improvement/tests/test_lesson_ranker.py` (10 tests). |
| File intent conflict detection (file + directory overlap) | `change-management/parallel-execution` | `modules/concurrency/store.py` (check_conflicts: file overlap + directory containment) | Reports conflicts; does not block. Tested: `tests/test_concurrency.py` (5 intent tests). |
| Parallel worker state tracking | `change-management/parallel-execution` | `modules/parallel_coordinator/store.py` (get_worker_status: pending/running/completed/stopped/failed) | Reports per-plan worker states. Tested: `tests/test_parallel_coordinator.py` (12 tests). |
| Coordination messages between workers | `change-management/parallel-execution` | `modules/concurrency/store.py` (send_message, get_messages) | Advisory inter-worker communication. Tested: `tests/test_concurrency.py` (2 message tests). |
| Intent router auto-classifies user requests | `skill-routing/intent-router` | `skills/skill-routing/intent-router/SKILL.md` (9 intent categories, confidence scoring) | Advisory classification; explicit `/skill-name` overrides. |

---

## Guideline (prose instruction only)

| Rule | Stated in (skill) | Target enforcement (v4) |
|---|---|---|
| New tests detect the change (red/green check) | `testing/test-implementation/suite-authoring` | `red_green_check.py` (§9 item 10): fails on base, passes on head |
| New-test flake gate (N random-order runs, 0 flakes) | `testing/test-implementation/suite-authoring` | `flake_gate.py` (§9 item 10) |
| Diff-scoped mutation score | `testing/test-implementation/suite-authoring` | `mutation_adapters.json` + DoD `mutation` gate at MEDIUM+ (§9 item 10) |
| No agent EXTERNAL_MUTATION / DEPLOY | `change-management/parallel-execution` | No sandbox/network policy shipped; operation classes absent from role tool surface but unenforced at runtime |
| qa-derive implementation-blindness (Copilot, Bash) | `roles/qa-derive` | Enforced on Claude Code Edit/Write/Read; not enforceable on Copilot (no path-deny primitive) or via Bash. Route blind roles to Claude Code or sandbox (§9 item 9). |
| 3-attempt iteration cap | `grounding/agent-failure-modes` | Server-side `record_task_failure` enforces ITERATION_CAP=3. Promoted to **Enforced** — see Enforced table (ASI06). Client-side `maxTurns` remains a guideline. |
| AC coverage → DONE | `product-planning/definition-of-done` | Needs `ledger_cli.py ingest-ac-coverage` and `export-planning-evidence` (§9 item 2) which do not exist yet |
| Rule of Two scoping (no session holds untrusted + secrets + mutation) | `governance/permission-scoping` | Designed; no runtime enforces session-level scoping. Developer role has Bash + reads untrusted issues + network. Vendor sandbox is the target primitive. |
| Tracker projection (agents never write the tracker; CI projects) | `roles/product-planner` | `tools/tracker_projection.py` does not exist (§9 item 2) |
| Impact-plan vs actual diff comparison | `testing/test-implementation/suite-authoring` | Promoted to **Enforced** — see Enforced table |
| Control-file CRITICAL on Copilot | `governance/default-permissions` | Copilot has no path-deny primitive; denials are prose in `.agent.md` — instructed, not enforced |
| Worktree isolation per task | `change-management/change-set` | Promoted to **Enforced** — see Enforced table |
| Handoff schema validation (source on FACT, input_references on INFERENCE) | `grounding/evidence-gate` | Promoted to **Enforced** — see Enforced table |
| Contract drift detection | `contracts/drift-detection` | Classification scheme exists; no CI job or periodic runner |
| Autonomy gated by verification strength | `governance/autonomy-gating` | Target: branch ruleset requiring review in ASSIST repos |
| Reviewer model-family diversity for HIGH/CRITICAL | `roles/reference/reviewer-diversity.md` | Target: server check on `record_handoff` |
| Brownfield conventions (Copilot) | `engineering-design/project-conventions` | Enforced by the project's own CI, not by the platform on Copilot |
| Circuit breaker (emergency stop via `.adlc/STOP`) | `grounding/circuit-breaker` | Target: PreToolUse hook checks for `.adlc/STOP`; halt event written to journal |
| Discovery bounds (question/round limits) | `grounding/agent-failure-modes` | Orchestrator-tracked counter; documented in `reference/discovery-bounds.md` |
| Tool safety bounds (read/bash/grep limits) | `grounding/trust-boundaries` | Host tools enforce natively; documented in `reference/tool-safety-bounds.md` |
| Context assembly order (5-layer deterministic) | `skill-routing/context-assembly` | Documented protocol; no runtime enforcer yet |
| Content fence protocol (escape-resistant delimiters) | `grounding/content-fence` | Documented protocol; applied by context-assembly mechanism |
| Host parity invariant (same capabilities regardless of host) | `docs/cross-cutting-design-rules.md` | Architectural principle; CI target: verify parity across host outputs |
| Role quality rubrics (self-scoring before handoff) | `roles/*` | Self-assessment checklist in each ROLE.md; threshold triggers self-revision |
| Structured reasoning trail (4-channel notes) | `core/evidence-ledger` | Documented in `reference/structured-reasoning.md`; extends evidence ledger |
| Document visibility classification (INTERNAL/DELIVERABLE) | `docs/cross-cutting-design-rules.md` | Target: PostToolUse hook checks INTERNAL content not in output |
| ADLC workspace manager (`.adlc/` structured storage) | `docs/workspace-layout.md` | Documented layout; `.adlc/` auto-added to `.gitignore` |
| Workspace isolation (worktree per worker) | `workflow/workspace-isolation` | Documented protocol; isolation rules, handback, branch conventions |
| Worker sandbox policy (env allowlist, command restrictions) | `change-management/parallel-execution` | Documented in `reference/worker-sandbox-policy.md`; target: managed-settings enforcement |
| Stage transition engine (advisory, not blocking) | `workflow/stage-preflight` | Validates transitions; does not prevent MCP tool calls. Target: gate hooks |
| ADLC Insight Hub (observability dashboard) | `docs/cross-cutting-design-rules.md` | Web UI served from MCP server; read-only views of all module data |
| ADLC CLI toolkit (8 command wrappers) | `docs/workspace-layout.md` | CLI scripts under `cli/`; wrappers for MCP module operations |

---

## Notes

- Every row in "Enforced" names a test. If the test is removed or the artifact path changes,
  this table must be updated. A CI check (v4 §9 item 19) will verify that every Enforced
  artifact path exists and every named test file exists.
- "Detects" items are scheduled for gate wiring in v4 §9.
- "Guideline" items that say "no enforcement point yet" have a target in the v4 plan; the
  remaining ones are structural limitations of the vendor platforms.
