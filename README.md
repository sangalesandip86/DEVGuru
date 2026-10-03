# DEVGuru — AI ADLC Platform

An AI-agent platform for the software development lifecycle, built as a catalog of
**skills**, **subagent roles**, **enforcement hooks**, and one **MCP server**, designed to run
inside Claude Code and GitHub Copilot-class coding assistants.

The unit of work is the **Change Set** — a requirement plus every repo, contract, and
environment it touches, pinned to a snapshot. For single-repo work the issue + PR on the forge
*is* the Change Set. Reasoning is evidence-grounded: every claim in a structured artifact
traces to a source, or it becomes a QUESTION or an expiring ASSUMPTION.

Source plan: [docs/ai-sdlc-platform-plan-v3.1.md](docs/ai-sdlc-platform-plan-v3.1.md)
(v3 kept for history: [docs/ai-sdlc-platform-plan-v3.md](docs/ai-sdlc-platform-plan-v3.md)).
Architecture decisions: [ADR 0001 — modular-monolith MCP server](docs/adr/0001-mcp-modular-monolith.md),
[ADR 0002 — product planning layer](docs/adr/0002-product-planning-layer.md),
[ADR 0003 — test engineering & test data](docs/adr/0003-test-engineering-and-data.md),
[ADR 0005 — follow existing project standards](docs/adr/0005-follow-existing-project-standards.md).
Authoring rules: [docs/authoring-conventions.md](docs/authoring-conventions.md).

## Core rules in one table

| Rule | Enforced by |
|---|---|
| Agents set `REVIEWED`; the server sets `VERIFIED` from machine evidence; only humans set `APPROVED` | MCP tool surface — no agent tool writes APPROVED/INTEGRATED/RELEASED |
| Control files (hooks, agent/skill/MCP config, AGENTS.md, CLAUDE.md, CODEOWNERS, CI) are never agent-writable | Managed settings + `control-file-guard` hook |
| FACT entries come from hooks, never from model self-report | `fact-writer` PostToolUse hook |
| Brownfield work follows the project's own standards; new dependencies need a DECISION + `human:tech-lead` APPROVAL (§4.15) | Project lint/conformance in CI + `dependency-decision-check` + CODEOWNERS |
| Untrusted input is data | Rule of Two session scoping + per-role tools |
| Unknown → more scrutiny | Fail-safe defaults (`grounding/ambiguity-escalation`) |

Full mapping: [docs/enforcement-map.md](docs/enforcement-map.md).

## Layout

```
skills/
  grounding/          binding, cross-cutting — evidence-gate, ambiguity, trust, failure modes, review format
  product-planning/   plan-as-code (plans/**), story types, DoR/DoD policies (control files), planning skills
  self-improvement/   binding — failure-capture, human-gated improvement-review
  core/               evidence-ledger, fact-classification
  enforcement/        NOT skills — hooks, managed-settings templates, CI checks, tests
  mcp-servers/        adlc-mcp: one MCP server ("adlc"), modules evidence_ledger / change_management / contract_registry
  skill-routing/      two-phase router, binding-vs-advisory, token budget
  change-management/  change-set, snapshot, dependency-discovery, risk-tiering, parallel-execution
  contracts/          registry, compatibility-check, drift-detection
  roles/              tool-neutral role specs + generator (role.yaml → dist/)
  testing/            test design (qa-derive oracle) + test implementation (test-engineer binding) + test data (§4.13), test architecture, UI/mobile/API/perf/security, AI-agent testing (OWASP ASI)
  engineering-design/ project-conventions (brownfield conformance, §4.15 — required for ARCHITECTURE/DESIGN/IMPLEMENT on existing repos), code design, architecture, data store / messaging selection
  ai-integration/     prompt engineering, LLM integration, RAG
  governance/         default-permissions, autonomy-gating, permission-scoping, policy-drift-check
dist/                 generated .claude/agents and .github/agents — never hand-edited
docs/                 plan, conventions, enforcement map, tool compatibility, pilot measurement
```

## Phases

| Phase | Delivers | Key artifacts |
|---|---|---|
| 0 | Evidence ledger, grounding, enforcement, path-based risk tiers, default permissions | `core/`, `grounding/`, `enforcement/`, `governance/default-permissions/`, `adlc-mcp` evidence_ledger module |
| 1 | Product Planning core (policies, intake, story-writer, refinement, DoR/DoD, planning gates), routing, forge-native single-repo Change Sets, first roles incl. product-planner and test-engineer, test engineering core (§4.13), self-improvement, security + AI-agent testing | `product-planning/`, `enforcement/ci-checks/planning-gates/`, `skill-routing/`, `testing/{test-design,test-implementation,test-data}/`, `enforcement/ci-checks/test-integrity/`, `roles/{product-planner,test-engineer,developer,qa-derive,qa-diagnose,code-reviewer}`, `self-improvement/`, `testing/{security,ai-agent}-testing/` |
| 2 | Multi-repo / parallel Change Sets; Product Planning full | `change-management/`, `product-planning/` (full), change_management module |
| 3 | Contracts, remaining roles and governance | `contracts/`, contract_registry module, `roles/{product-owner,architect,security-reviewer}` |

Degraded Mode: when a required role isn't built yet, the Change Set routes to a **named human**
standing in for it — never a silent skip, never an indefinite block (plan §2).

## Installing

Enforcement ships from an **organization-managed** location, not from each repo.

### Claude Code
1. Install `skills/enforcement/` to an admin-owned path; deploy
   `skills/enforcement/managed-settings/templates/claude-code-managed-settings.json` as managed
   settings (replace `{{ADLC_ENFORCEMENT_DIR}}`).
2. Register the MCP server `adlc` (`skills/mcp-servers/adlc-mcp/`); tools appear as
   `mcp__adlc__<tool>`. One credential per role.
3. Install skills as Claude Code skills (each `SKILL.md` folder) — or package each top-level
   `skills/<group>` as a plugin.
4. Copy `dist/claude/.claude/agents/*.md` into the target repo (via CODEOWNERS-reviewed PR).
5. In each repo: `AGENTS.md` + one-line `CLAUDE.md` (`@AGENTS.md`).

### GitHub Copilot
1. Apply the org controls in `skills/enforcement/managed-settings/templates/copilot-org-controls.md`.
2. Add `.github/hooks/hooks.json` from `skills/enforcement/hooks/registration/copilot-hooks.json`.
3. Skills → `.github/skills/`; agents from `dist/copilot/.github/agents/*.agent.md`.
4. Register MCP server `adlc`. Handoffs on the Copilot cloud agent go through MCP, not the
   native handoff feature (see [docs/tool-compatibility.md](docs/tool-compatibility.md)).

## Build sequence status (plan v3.1 §9)

- [x] 1. Control-files definition + managed-settings denial — `governance/default-permissions/reference/control-file-paths.json`, `enforcement/managed-settings/`
- [x] 2. `AGENTS.md` + `CLAUDE.md` shim + CI check — root files, `enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py`
- [x] 3. `/core` + `/grounding` + `/enforcement` — scaffolded
- [x] 4. Evidence Ledger MCP (module of `adlc-mcp`) — scaffolded; needs pilot auth wiring
- [x] 5. Path-based risk-tier lookup — `change-management/risk-tiering/path-tiers.json`
- [x] 6. `/governance/default-permissions`
- [x] 7. `/skill-routing`
- [x] 8. Minimum `/roles` + handoff-schema + conflict-resolution
- [ ] 8a. Product Planning core (v3.1) — policies registered as control files ✔ (`control-file-paths.json` `planning-policies`); skills + `planning-gates` CI checks + tracker-projection job in progress
- [x] 9. `/self-improvement`
- [ ] 9a. Test engineering core (v3.1 §4.13) — `test-engineer` role, discovery scripts, test-case-design, bdd-feature-authoring, test-data-synthesis, suite-authoring, bdd-step-binding; CI checks in `enforcement/ci-checks/test-integrity/` (integrity guard, fixture PII scan, red/green, new-test flake gate, no-fixed-sleep). Required before any agent updates an existing suite.
- [x] 10. `/testing/security-testing` + `/testing/ai-agent-testing`
- [ ] 11. `/change-management` + change_management module — scaffolded; enable when multi-repo work appears
- [ ] 12. Populate `/testing`, `/engineering-design`, `/ai-integration` progressively
- [ ] 13. `/contracts` + contract_registry module + remaining roles/governance — scaffolded; enable in Phase 3
- [ ] 14. Baseline the five pilot metrics — template in [docs/pilot-measurement.md](docs/pilot-measurement.md)
- [x] 15. Tool-specific generator — `skills/roles/scripts/generate_agents.py` → `dist/`

"Scaffolded" means the artifacts exist; nothing here has run against a real pilot repo yet.

## Tests

```sh
python -m unittest discover -s skills/enforcement/tests -v
```
