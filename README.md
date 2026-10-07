# DEVGuru — AI ADLC Platform

An AI-agent platform for the software development lifecycle, built as a catalog of
**skills**, **subagent roles**, **enforcement hooks**, and one **MCP server**, designed to run
inside Claude Code and GitHub Copilot-class coding assistants.

The unit of work is the **Change Set** — a requirement plus every repo, contract, and
environment it touches, pinned to a snapshot. For single-repo work the issue + PR on the forge
*is* the Change Set. Reasoning is evidence-grounded: every claim in a structured artifact
traces to a source, or it becomes a QUESTION or an expiring ASSUMPTION.

Source plan: [docs/ai-sdlc-platform-plan-v4.md](docs/ai-sdlc-platform-plan-v4.md)
(v3.1 and v3 kept for history).
Full review: [docs/review/2026-10-03-platform-review.md](docs/review/2026-10-03-platform-review.md).
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
   Use `claude mcp add-json --scope local` for auto-start (no approval prompt):
   ```bash
   claude mcp add-json --scope local adlc '{
     "command": "<python-path>",
     "args": ["-m", "adlc_mcp"],
     "env": {
       "PYTHONPATH": "<repo>/skills/mcp-servers/adlc-mcp/src",
       "ADLC_MODULES": "evidence_ledger,change_management,contract_registry,work_planning,event_journal,stage_engine,concurrency,parallel_coordinator",
       "ADLC_SKILLS_ROOT": "<repo>/skills",
       "ADLC_TOKEN": "<your-token>"
     }
   }'
   ```
   Verify with `claude mcp get adlc` — should show `✔ Connected`.

   **MCP config locations (Claude Code 2.1+):**
   - `local` scope → `~/.claude.json` (per-project, auto-start, no approval)
   - `project` scope → `<repo>/.mcp.json` (shared, requires one-time approval)
   - **Not read** for MCP: `.claude/settings.json` `mcpServers` key (hooks/permissions only),
     `~/.claude/.mcp.json` (stale in 2.1+)
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

## Build sequence status (v4 §9)

Legend: `[x]` exists and tested; `[~]` exists with noted gaps; `[ ]` absent.

- [x] 1. Control-files definition + managed-settings denial — gaps: `skills/**`/`dist/**` globs overreach in target repos (split platform/target planned)
- [x] 2. `AGENTS.md` + `CLAUDE.md` shim + CI check
- [~] 3. `/core` + `/grounding` + `/enforcement` — gaps: fact-writer stores raw file content (no redaction); `record_handoff` does not validate `source`/`input_references`; enforcement map overclaimed (now fixed as three-column)
- [~] 4. Evidence Ledger MCP — gaps: no SYSTEM write path (VERIFIED unreachable); no workspace anchoring; `source_type` caller-supplied; credentials have no expiry
- [~] 5. Path-based risk-tier lookup — gap: second path-tier table inside MCP `change_management` module disagrees with `path-tiers.json`
- [~] 6. `/governance/default-permissions` — gaps: managed-settings key placement unverified; missing `allowManagedMcpServersOnly`, `strictKnownMarketplaces`, `disableSkillShellExecution`; no deployed-vs-template check
- [~] 7. `/skill-routing` — gap: no `route.py` script; mandatory routing is prose; no `paths:` frontmatter on stack skills
- [x] 8. Minimum `/roles` + handoff-schema + conflict-resolution — gaps: generated subagents lack `maxTurns`/`disallowedTools`/`isolation`; Copilot agents carry denials as prose (instructed, not enforced)
- [~] 8a. Product Planning core — gaps: AC hash diverges between planning-gates and MCP `work_planning`; `export-planning-evidence`/`record-planning-status`/`ingest-ac-coverage` CLI commands missing; tracker projection absent; single-repo `planning` resolves MISSING
- [~] 9. `/self-improvement` — gaps: incident/lesson JSON schemas differ from MCP validation; no test that sanitizer blocks glossary terms
- [~] 9a. Test engineering core — gaps: `red_green_check.py`, `flake_gate.py` are Markdown stubs (no scripts); mutation testing absent; `test_integrity_guard --overrides` reads from head/ (agent-writable); `impact_plan_check.py` missing; fingerprint tables ~10x smaller than Renovate
- [~] 10. `/testing/security-testing` + `/testing/ai-agent-testing` — gap: no harness runs the AI-agent-testing catalogs in CI
- [~] 11. `/change-management` + module — gaps: approvals not epoch-scoped; BLOCKED exits incomplete; two path-tier engines; `dependency-decision-check` not wired to gates
- [~] 12. `/testing`, `/engineering-design`, `/ai-integration` — gap: description/size budgets unenforced; stack skills lack `paths:` scoping
- [~] 13. `/contracts` + module + remaining roles — gap: Phase 3 CI wiring absent
- [ ] 14. Baseline the five pilot metrics — `metrics_export.py` absent; template in [docs/pilot-measurement.md](docs/pilot-measurement.md)
- [x] 15. Tool-specific generator — gaps: needs spec-currency CI check
- [ ] 16. `repo-facts` shared engine — absent; four scanners parse manifests independently
- [ ] 17. Signed releases / SBOM / SLSA L2 — absent
- [ ] 18. AI-authorship + run-id trailers + CI check — absent
- [ ] 19. Enforcement-claim CI check — absent (Enforced rows must name a test)
- [ ] 20. Skill catalog consolidation 83 → 31 — planned; see review Appendix B

All 83 test suites pass (enforcement: 40, MCP: 82, planning-gates: 31). No item has run against a real pilot repo yet.

## Insight Hub UI Setup

The ADLC MCP server ships with a built-in web dashboard called **Insight Hub**.
The installer (`python installer/install.py`) handles skills + MCP wiring but
does not yet issue credentials or start the UI — follow these steps manually.

### 1. Issue a credential (one-time)

Sets up `~/.adlc/credentials.json` with a hashed token. The plaintext token is
printed once — save it.

**PowerShell (Windows):**
```powershell
$env:PYTHONPATH = "skills\mcp-servers\adlc-mcp\src"
python -c "from adlc_mcp.kernel.identity import issue_credential; token = issue_credential('HUMAN', 'sandip', human_roles=['human:tech-lead']); print(f'Your token: {token}')"
```

**Bash (macOS/Linux):**
```bash
PYTHONPATH=skills/mcp-servers/adlc-mcp/src \
python3 -c "from adlc_mcp.kernel.identity import issue_credential; token = issue_credential('HUMAN', 'sandip', human_roles=['human:tech-lead']); print(f'Your token: {token}')"
```

Valid `human_roles` (must include the `human:` prefix):
`human:tech-lead`, `human:security-lead`, `human:product-owner`, `human:release-manager`

### 2. Start the UI server

**PowerShell (Windows):**
```powershell
$env:PYTHONPATH = "skills\mcp-servers\adlc-mcp\src"
$env:ADLC_MODULES = "evidence_ledger,change_management,contract_registry,work_planning,event_journal,stage_engine,concurrency,parallel_coordinator"
$env:ADLC_TOKEN = "<paste-your-token-here>"

python -m adlc_mcp --serve-ui --port 8080
```

**Bash (macOS/Linux):**
```bash
export PYTHONPATH=skills/mcp-servers/adlc-mcp/src
export ADLC_MODULES=evidence_ledger,change_management,contract_registry,work_planning,event_journal,stage_engine,concurrency,parallel_coordinator
export ADLC_TOKEN=<paste-your-token-here>

python3 -m adlc_mcp --serve-ui --port 8080
```

Open **http://127.0.0.1:8080/ui/** in your browser.

UI views: **Dashboard** (overview), **Workspace** (repos), **Work Item** (change sets/tasks),
**Trace** (evidence ledger + stage transitions), **Parallel** (coordinator activity).

### 3. Terminal dashboard (alternative)

```powershell
# PowerShell
$env:PYTHONPATH = "skills\mcp-servers\adlc-mcp\src"
python skills\mcp-servers\adlc-mcp\cli\adlc_watch.py --db .adlc\event_journal.db
```

```bash
# Bash
PYTHONPATH=skills/mcp-servers/adlc-mcp/src \
python3 skills/mcp-servers/adlc-mcp/cli/adlc_watch.py --db .adlc/event_journal.db
```

### Common issues

| Error | Fix |
|---|---|
| `no credential presented` | `$env:ADLC_TOKEN` not set — PowerShell uses `$env:VAR`, not `set VAR=` (cmd) |
| `credential not recognised` | Token not in `~/.adlc/credentials.json` — re-run step 1 |
| `invalid human role 'tech-lead'` | Use the full prefixed form: `human:tech-lead` |
| `ModuleNotFoundError: adlc_mcp` | `PYTHONPATH` not set or wrong — must point to `skills/mcp-servers/adlc-mcp/src` |

## Tests

```sh
python -m unittest discover -s skills/enforcement/tests -v
```
