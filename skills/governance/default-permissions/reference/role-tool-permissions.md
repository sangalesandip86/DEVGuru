# Role → Tool Permissions

Plan §4.11. Plan v3.1 adds product-planner (§4.12) and test-engineer (§4.13). Authority values follow §5.5: agents may set `REVIEWED`; only the server sets
`VERIFIED` (from machine evidence); only an authenticated human sets `APPROVED`.

| Role | Can Read | Can Modify | Can Deploy | Can Set | Restrictions |
|---|---|---|---|---|---|
| developer | repos in Change Set | repos in Change Set scope | No | — | Cannot modify files outside scope; no production access. Follows existing project standards (v3.1 §4.15): a new dependency or changed architectural boundary needs a DECISION (short ADR, architect `REVIEWED`) **and** `human:tech-lead` APPROVAL at any tier — enforced by `dependency-decision-check` + CODEOWNERS |
| qa-derive | requirements + acceptance criteria + test files | `plans/test-designs/**`, `**/*.feature`, test files | No | `REVIEWED` on test design | Implementation paths **technically denied**, not just discouraged — still implementation-blind (v3.1 §4.13: the oracle) |
| test-engineer | all repos in Change Set (incl. app source) | test assets only (fixtures, page objects/robots, step definitions, specs) | No | `REVIEWED` on test implementation fidelity | **Write-denied** on app source, `plans/test-designs/**` and `**/*.feature`; testability hooks are *proposed* to developer, never added (v3.1 §4.13: binding, not oracle) |
| qa-diagnose | all repos + test results + logs/traces | test files only | No | `REVIEWED` on diagnosis | Cannot modify implementation code |
| code-reviewer | all repos in Change Set | None | No | `REVIEWED` on code quality | Read-only |
| security-reviewer | all repos + dependency data | None | No | `REVIEWED` (ACCEPT/REJECT) | REJECT blocks within domain; cannot APPROVE alone |
| architect | all repos + contracts | architecture docs only | No | `REVIEWED` on design | Cannot modify implementation code. `REVIEWED` on a deviation ADR (new dependency/framework, pattern, layer, data store, top-level module) is necessary but never sufficient: a new dependency or boundary change also needs `human:tech-lead` APPROVAL (v3.1 §4.15) |
| product-owner | requirements + acceptance criteria | requirements only | No | marks `READY_FOR_APPROVAL` | Cannot APPROVE — human-only |
| product-planner | requirements + plans + repos | `plans/**` only | No | `REVIEWED` on decomposition | Never sets story status (READY/DONE/ACCEPTED); no tracker tools — tracker sync is a CI SYSTEM job |
| **ALL agent roles** | — | — | **No** | **Never**: `APPROVED`, `INTEGRATED`, `RELEASED`, story `READY`/`DONE`/`ACCEPTED`, or any control-file write | Enforced via managed settings, not instruction |

## Operation classes per role

| Role | READ | WORKSPACE_WRITE | REPO_WRITE | EXTERNAL_MUTATION | DEPLOY |
|---|---|---|---|---|---|
| developer | ✔ | ✔ | ✔ (branch only) | ✘ | ✘ |
| qa-derive | ✔ (non-impl paths) | ✔ (tests, test designs, .feature) | ✔ (tests, test designs, .feature) | ✘ | ✘ |
| test-engineer | ✔ | ✔ (test assets) | ✔ (test assets) | ✘ | ✘ |
| qa-diagnose | ✔ | ✔ (tests) | ✔ (tests) | ✘ | ✘ |
| code-reviewer | ✔ | ✘ | ✘ | ✘ | ✘ |
| security-reviewer | ✔ | ✘ | ✘ | ✘ | ✘ |
| architect | ✔ | ✔ (arch docs) | ✔ (arch docs) | ✘ | ✘ |
| product-owner | ✔ (requirements) | ✔ (requirements) | ✔ (requirements) | ✘ | ✘ |
| product-planner | ✔ | ✔ (`plans/**`) | ✔ (`plans/**`) | ✘ (no tracker writes) | ✘ |

`EXTERNAL_MUTATION` and `DEPLOY` belong to CI and the server only, triggered by an observed,
authorized forge event (§4.5, §5.10).

## MCP tool surface per credential (Server 1)

| Tool | Agent credentials | Hook/system credential | Human credential |
|---|---|---|---|
| `record_evidence` | ✔ (non-FACT classifications only) | ✔ (FACT) | ✔ |
| `query_evidence` | ✔ | ✔ | ✔ |
| `record_incident` | ✔ | ✔ | ✔ |
| `query_incidents` | ✔ | ✔ | ✔ |
| `record_correction` | ✔ | ✔ | ✔ |

No tool on any server sets `APPROVED`, `INTEGRATED`, or `RELEASED` for an agent-authenticated
caller; those transitions come only from `ingest_forge_event` (Server 2) or an authenticated
human action.

## Native mapping

| Platform | Where the row is applied |
|---|---|
| Claude Code | Subagent `tools:` frontmatter, per-agent MCP server scoping, `permissions.deny` in managed settings |
| GitHub Copilot | `.agent.md` `tools:` config, per-agent MCP scoping, org-level policies |

Generated agent files under `dist/` are produced from `skills/roles/*/role.yaml`, which must
stay consistent with this table.
