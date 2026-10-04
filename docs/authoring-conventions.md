# Authoring Conventions

Shared rules for every artifact in this repository. The source plan is
[`ai-sdlc-platform-plan-v3.1.md`](ai-sdlc-platform-plan-v3.1.md) (v3 kept for history); section numbers (§) refer to v3.1.

## Layout

The catalog lives under `skills/` and mirrors plan §3 exactly. Additions beyond §3 are
limited to what the plan requires but the tree omits (MCP server implementations, the
Phase 0 path-tier lookup, the role generator, shared schemas).

| Path | Contents |
|---|---|
| `skills/<group>/<skill>/SKILL.md` | One skill — an instruction document, never executable logic |
| `skills/<group>/<skill>/reference/*.md` | Detail loaded on demand by the skill |
| `skills/<group>/<skill>/scripts/*.py` | Tool invocations the skill tells the agent to run |
| `skills/roles/<role>/role.yaml` + `ROLE.md` | Tool-neutral role spec (plan §8 "author once") |
| `skills/enforcement/` | Hooks, managed-settings templates, CI checks — enforcement, not skills |
| `skills/mcp-servers/adlc-mcp/` | One deployable MCP server (modular monolith) hosting the three plan §6 servers as modules — see below |
| `dist/` | Generated `.claude/agents/*.md` and `.github/agents/*.agent.md` — never hand-edited |

## SKILL.md format

```markdown
---
name: <skill-dir-name>
description: <what it does + when to use it; trigger-oriented, one or two sentences>
metadata:
  group: <grounding|core|self-improvement|...>
  phase: <0|1|2|3|progressive>
  binding: <true|false>
  plan-ref: "§4.x"
  stage: <INTAKE|ARCHITECTURE|PLAN|DESIGN|IMPLEMENT|TEST|REVIEW|INTEGRATE|RELEASE|LEARN|CROSS_CUTTING>
  inputs: [<artifact kinds required, e.g. requirement, ready-story, test-design, change-set>]
  outputs: [<artifact kinds produced>]
  repo_roles: [<app|planning|tests|contracts|infra — repos this skill needs>]
---

# <Title>

## Purpose
## When this applies
## Preflight            (link to skills/workflow/stage-preflight/reference/standard-preflight.md;
                         list only skill-specific deltas — Inputs, ADOPT, BACKFILL, Repo roles)
## Procedure            (numbered steps the agent follows)
## Outputs              (which ledger classifications it produces, which handoff fields)
## Enforcement          (what actually enforces this — cite the §5.6 row, or state
                         "Guideline only — no enforcement point yet")
## References           (relative links to reference/*.md, scripts, related skills)
```

- Skills **inform**; they never claim to enforce. If a rule has an enforcement point, name it.
- Cross-reference other skills by relative path instead of restating their rules
  (every role references `grounding/evidence-gate`).
- Every `## Preflight` section links to `skills/workflow/stage-preflight/reference/standard-preflight.md`
  and lists only skill-specific deltas (Inputs, ADOPT, BACKFILL, Repo roles). Do not duplicate
  the shared preflight text.
- Content the plan marked "unchanged from v2" was reconstructed from v3 context.
  Markers have been reviewed and removed as of 2026-10-03.

## Shared vocabulary (do not invent variants)

- Workflow stages (plan §4.14; NOT build phases): `INTAKE ARCHITECTURE PLAN DESIGN IMPLEMENT TEST REVIEW INTEGRATE RELEASE LEARN` (+ `CROSS_CUTTING` for grounding/core/governance skills)
- Preflight outcomes: `SATISFIED ADOPT BACKFILL ASK BLOCK`
- Repo roles: `app planning tests contracts infra`; workspace manifest `adlc.workspace.yaml`; repo creation request `repo-request.yaml`
- Artifact kinds (for `inputs`/`outputs`): `source-doc requirement nfr-catalog glossary traceability-matrix system-map architecture-package adr contract epic ready-story milestone test-strategy test-design test-catalog conventions-catalog change-set test-suite review-verdict release-record incident lesson`

- Classifications: `FACT INFERENCE ASSUMPTION PROPOSAL QUESTION DECISION RISK`
- Lifecycle (entry-level): `DRAFT PROPOSED REVIEWED VERIFIED APPROVED REJECTED`
- Trust levels: `SYSTEM ORGANIZATIONAL REPOSITORY EXTERNAL_STRUCTURED EXTERNAL_UNSTRUCTURED`
- Actor types: `HUMAN AGENT SYSTEM`
- Risk tiers: `LOW MEDIUM HIGH CRITICAL`
- Change Set states: `DRAFT SCOPED PLANNED PLAN_APPROVED EXECUTING VERIFYING INTEGRATED RELEASED`
  + `BLOCKED FAILED CANCELLED ROLLED_BACK`
- Operation classes: `READ WORKSPACE_WRITE REPO_WRITE EXTERNAL_MUTATION DEPLOY`
- Retry policies: `RETRY STOP ESCALATE REPLAN RESUME`
- Escalation reason codes: `UNRESOLVED_DEPENDENCY UNKNOWN_BLAST_RADIUS SENSITIVE_PATH COMPATIBILITY_UNKNOWN`
- Human approvers: `human:tech-lead human:security-lead human:product-owner human:release-manager`
- Agent roles: `product-owner product-planner architect developer qa-derive qa-diagnose test-engineer security-reviewer code-reviewer`
- Test design artifacts: `plans/test-designs/ST-<n>.yaml` (scenario IDs `ST-<n>/SC-<n>`); test modes `A_SURGICAL B_MIRROR C_GREENFIELD`; impact-plan actions `CREATE UPDATE REUSE`
- Discovery outputs: `.adlc/catalog/stack.json`, `.adlc/catalog/test-assets.json`, `.adlc/catalog/step-patterns.json` (phrases only — the one catalog file qa-derive may read)
- Story states (derived, never agent-set): `DRAFT REFINING READY IN_PROGRESS IN_VERIFICATION DONE ACCEPTED` + `BLOCKED SPLIT CANCELLED`
- Story types: `FEATURE_STORY UI_STORY API_CONTRACT DATA_MIGRATION SECURITY_STORY INFRASTRUCTURE TECHNICAL_STORY REFACTOR BUG_FIX SPIKE TEST_AUTOMATION DOCUMENTATION`
- DoR/DoD check kinds: `STRUCTURAL JUDGMENT APPROVAL`; AC IDs: `ST-<n>/AC-<n>`; sizes: `XS S M L`
- Planning artifact IDs: `REQ-<n> EPIC-<n> FEAT-<n> ST-<n> MS-<n>`; files under `plans/<kind>s/<ID>.yaml`

## Integration contracts

- **MCP server = modular monolith.** Plan §6's three servers ship as one package and one
  process (`adlc-mcp`, MCP server name `adlc`). Each is a module under
  `skills/mcp-servers/adlc-mcp/src/adlc_mcp/modules/<evidence_ledger|change_management|contract_registry>/`
  that owns its own tables and its own SQLite file, and exposes only a public `api.py`.
  Other modules may import only that `api.py`. A test enforces this. Modules are enabled
  per phase with `ADLC_MODULES`. In role tool lists, MCP tools are written as
  `mcp:adlc.<tool>`, keeping the tool names from §6.
- **Ledger DB:** SQLite at `$ADLC_DATA_DIR/evidence_ledger.db` (default `.adlc/`), overridable with
  `$ADLC_LEDGER_DB`. Owned by the `evidence_ledger` module.
- **Hooks → ledger:** hooks write FACT entries with
  `python skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py append-fact` reading one JSON
  object on stdin: `{run_id, tool, source_type, content, source, change_set_id?}`.
  Identity is `actor_type=SYSTEM`, `actor_id=hook:<hook-name>`; trust level is derived from
  `source_type`, never supplied.
- **Control-file paths:** the single source of truth is
  `skills/governance/default-permissions/reference/control-file-paths.json`. Hooks, managed
  settings, and CI checks read or are generated from it.
- **Path-based risk tiers (Phase 0):** `skills/change-management/risk-tiering/path-tiers.json`
  + `scripts/path_tier_lookup.py`.

## Scripts

Python 3.10+, standard library only unless the MCP SDK is required, `argparse`, JSON on
stdout, non-zero exit on failure, no network calls.
