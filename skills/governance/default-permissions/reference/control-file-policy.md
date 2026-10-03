# Control-File Policy

Implements the control-files rule from plan §4.1 / §4.11.

## What is a control file
Anything that configures how agents behave or what gates apply: hooks, agent/skill/MCP
definitions, `AGENTS.md`, `CLAUDE.md`, `CODEOWNERS`, rulesets, CI workflow definitions, and
this platform's own `skills/` tree. The canonical glob list is
[control-file-paths.json](control-file-paths.json) — every enforcement artifact reads it.

## Rules
1. **Agents cannot write control files.** Denied at the **managed-settings** layer
   (organization-controlled, not repo-local). A project-local setting can be rewritten by
   anyone with repo write access, or by an injected agent with shell access — it is a
   suggestion, not a control.
2. **Any control-file write is `CRITICAL` tier**, regardless of what else is in the Change Set.
3. **Human approval is always required** — `VERIFIED` alone never suffices. Approval comes
   from an authenticated CODEOWNERS review on the PR.
4. **Every attempt is logged** by a `ConfigChange`-class hook regardless of outcome
   (`skills/enforcement/hooks/config-change-logger/`).

## Enforcement layers (defense in depth)

| Layer | Artifact | Blocks |
|---|---|---|
| Managed settings | `skills/enforcement/managed-settings/templates/` | Edit/Write tool calls to control paths, before any hook runs |
| PreToolUse hook | `skills/enforcement/hooks/control-file-guard/` | Edit/Write/MultiEdit/NotebookEdit and recognisable shell writes |
| CODEOWNERS + ruleset | repo `CODEOWNERS` → platform owners | Merge of any PR touching control paths without human review |
| CI check | `skills/enforcement/ci-checks/control-file-policy-check/` | Drift: managed deny list no longer covers every control glob; AGENTS.md without CLAUDE.md shim |

## Why this is day-one
Prompt injection inducing an agent to write a permissive setting into a repo-local config
file, then trusting that file, is a demonstrated, exploited vulnerability class against AI
coding agents. Enforcement — not scanning — is the point.

## Changing this policy
Edits to `control-file-paths.json` are themselves control-file writes: CRITICAL, human-only.
After editing, regenerate the managed-settings template
(`python skills/enforcement/managed-settings/generate_deny_list.py`) and run the CI check.
