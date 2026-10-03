# Enforcement Map — rule → skill → enforcement point

Plan v3.1 §5.6. "The skill says so" and "the platform enforces it" are different guarantees. A rule
stated in a skill with no row here is a **guideline the model can choose to follow**, not a
guarantee. Keep this table current whenever a rule is added; `governance/policy-drift-check`
verifies every artifact path below exists.

MCP paths are relative to `skills/mcp-servers/adlc-mcp/src/adlc_mcp/` (one server, `adlc`;
tools appear as `mcp__adlc__<tool>` in Claude Code).

| Rule | Stated in (skill) | Actually enforced by | Artifact |
|---|---|---|---|
| No agent sets `APPROVED` / `INTEGRATED` / `RELEASED` | `skills/grounding/`, plan §5.5 | MCP tool surface — no such tool exists for agent callers; transitions only via `ingest_forge_event` / authenticated human | `modules/evidence_ledger/tools.py`, `modules/change_management/` (`update_status` rejects agent callers), `kernel/identity.py` |
| Untrusted content is data, not instructions | `skills/grounding/trust-boundaries/` | Rule-of-Two session scoping (§5.9) + per-role tool scoping | `skills/governance/permission-scoping/SKILL.md`, `skills/roles/*/role.yaml` → `dist/` |
| Control files are never agent-writable | `skills/grounding/trust-boundaries/reference/control-files.md` | Managed settings (org-level) deny list + `PreToolUse` hook + CODEOWNERS/ruleset | `skills/governance/default-permissions/reference/control-file-paths.json`, `skills/enforcement/managed-settings/templates/claude-code-managed-settings.json`, `skills/enforcement/hooks/control-file-guard/control_file_guard.py`, `skills/enforcement/managed-settings/templates/copilot-org-controls.md` |
| Every control-file change attempt is logged | `skills/governance/default-permissions/reference/control-file-policy.md` | ConfigChange-class hook (portable: PreToolUse) | `skills/enforcement/hooks/config-change-logger/config_change_logger.py` |
| Control-file protection is actually deployed | `skills/governance/policy-drift-check/` | CI required status check | `skills/enforcement/ci-checks/control-file-policy-check/check_control_file_policy.py`, `skills/enforcement/managed-settings/generate_deny_list.py --check` |
| Every AGENTS.md has a `@AGENTS.md` CLAUDE.md shim | `docs/tool-compatibility.md` (plan §8) | CI check | `skills/enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py` |
| QA Pass 1 is implementation-blind | `skills/roles/qa-derive/` | Tool permission denial on implementation paths, not instruction | `skills/roles/qa-derive/role.yaml` → `dist/claude/.claude/agents/qa-derive.md`, `dist/copilot/.github/agents/qa-derive.agent.md` |
| FACT entries are grounded | `skills/core/fact-classification/` | Hooks write FACT entries directly; model never self-reports a FACT | `skills/enforcement/hooks/fact-writer-hooks/fact_writer.py` → `skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py append-fact` |
| Agent identity is authentic; `trust_level` never caller-supplied | `skills/core/evidence-ledger/reference/identity-and-auth.md` | Server-side derivation from the authenticated connection | `kernel/identity.py`, `modules/evidence_ledger/domain.py` |
| Ledger is append-only and tamper-evident | `skills/core/evidence-ledger/reference/ledger-entry-schema.md` | Hash chain + no update/delete tool; corrections only via `record_correction` | `modules/evidence_ledger/store.py`, `modules/evidence_ledger/migrations/0001_initial.sql` |
| 3-attempt iteration cap, scoped by failure class | `skills/grounding/agent-failure-modes/` | Orchestrator-enforced counter (`tasks[].attempts` in the Change Set) | `modules/change_management/` (Phase 2); Phase 0–1: **guideline only** for single-repo forge-native work |
| No agent `EXTERNAL_MUTATION` / `DEPLOY` | `skills/change-management/parallel-execution/` | Operation classes absent from every role's tool surface | `skills/governance/default-permissions/reference/role-tool-permissions.md`, `skills/roles/*/role.yaml` |
| Risk tier always computable (Phase 0) | `skills/change-management/risk-tiering/` | Path-based lookup; unknown → HIGH | `skills/change-management/risk-tiering/path-tiers.json`, `skills/change-management/risk-tiering/scripts/` |
| Story is READY only when the DoR is met (v3.1) | `skills/product-planning/definition-of-ready/` | `readiness-gate` CI job (SYSTEM) over the merged plan + ledger; plan files have no status field | `skills/enforcement/ci-checks/planning-gates/readiness_gate.py`, `skills/product-planning/policies/dor-policy.yaml` |
| Story is DONE only when the DoD is met (v3.1) | `skills/product-planning/definition-of-done/` | `completion-gate` + `ac-coverage` CI jobs; agents have no status-setting tool | `skills/enforcement/ci-checks/planning-gates/completion_gate.py`, `skills/enforcement/ci-checks/planning-gates/ac_coverage.py`, `skills/product-planning/policies/dod-policy.yaml` |
| AC are frozen once READY (v3.1) | `skills/product-planning/story-writer/` | `plan-lint` diffs the AC hash of READY stories; mismatch forces REFINING and invalidates qa-derive `REVIEWED` | `skills/enforcement/ci-checks/planning-gates/plan_lint.py` |
| Planner cannot write the tracker (v3.1) | `skills/roles/product-planner/` | Role tool scope (no tracker tools); tracker sync runs only as a CI SYSTEM job | `skills/roles/product-planner/role.yaml`, `skills/governance/default-permissions/reference/role-tool-permissions.md` |
| DoR/DoD/story-type policy is not agent-weakenable (v3.1) | `skills/product-planning/policies/` | Listed explicitly in `control-file-paths.json` → managed-settings deny + `control-file-guard` | `skills/governance/default-permissions/reference/control-file-paths.json` (`planning-policies`), `skills/enforcement/managed-settings/templates/claude-code-managed-settings.json` |
| Test expectations come from AC, not code (v3.1 §4.13) | `skills/testing/test-design/test-case-design/`, `skills/roles/qa-derive/` | qa-derive implementation-path denial; test-engineer write-denied on `plans/test-designs/**` and `**/*.feature` | `skills/roles/qa-derive/role.yaml`, `skills/roles/test-engineer/role.yaml`, `skills/governance/default-permissions/reference/role-tool-permissions.md` |
| Agents don't weaken tests to go green (v3.1) | `skills/testing/test-implementation/suite-authoring/` | `test-integrity-guard` CI check — an expectation change requires an AC-hash change | `skills/enforcement/ci-checks/test-integrity/test_integrity_guard.py` |
| New tests actually detect the change (v3.1) | `skills/testing/test-implementation/suite-authoring/` | `red-green-check` CI job (fails on base, passes on head) + diff-scoped mutation score + new-test flake gate (5 random-order runs, 0 flakes) | `skills/enforcement/ci-checks/test-integrity/red_green_check.md`, `skills/enforcement/ci-checks/test-integrity/new_test_flake_gate.md` |
| No fixed sleeps in tests (v3.1) | `skills/testing/web-ui-automation/*`, `skills/testing/mobile-automation/*` | Lint rules + banned-API check in CI | `skills/enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py` |
| No real PII / production data / secrets in fixtures (v3.1) | `skills/testing/test-data/test-data-synthesis/` | `fixture-pii-scan` + secret-scanning CI checks; secrets referenced by name only | `skills/enforcement/ci-checks/test-integrity/fixture_pii_scan.py`, `skills/testing/security-testing/secret-scanning/` |
| Brownfield work follows existing project standards (v3.1 §4.15) | `skills/engineering-design/project-conventions/` | Project's own lint/format/type/arch-conformance in CI (VERIFIED); manifest-diff-without-DECISION flag; code-reviewer `REVIEWED` against `conventions.json` + golden files; CODEOWNERS routes manifests to `human:tech-lead` | `skills/enforcement/ci-checks/dependency-decision-check/check_dependency_decisions.py`, `skills/engineering-design/project-conventions/`, `skills/roles/code-reviewer/` |

## Rules that are guidelines only (no enforcement point yet)

| Rule | Skill | Target enforcement |
|---|---|---|
| Autonomy gated by verification strength | `skills/governance/autonomy-gating/` | Branch ruleset requiring review in `ASSIST` repos |
| Reviewer model-family diversity for HIGH/CRITICAL | `skills/roles/reference/reviewer-diversity.md` | Server check on `record_handoff`: reviewer `model_id` family ≠ developer's |
| Evidence-gate on structured artifacts | `skills/grounding/evidence-gate/` | Schema validation of handoffs (`source` required for FACT, `input_references` for INFERENCE) in `record_handoff` |
