# /enforcement — Phase 0

**Not skills.** Skills inform; these artifacts enforce (plan §1, §5.6). Everything here must
ship from a **managed / organizational source**, not as an editable part of each repo's
plugin install — otherwise a repo contributor or an injected agent can switch it off.

| Path | What it enforces |
|---|---|
| `hooks/control-file-guard/` | PreToolUse — denies agent writes to control files |
| `hooks/fact-writer-hooks/` | PostToolUse — writes FACT ledger entries from tool output (model never self-reports FACTs) |
| `hooks/config-change-logger/` | ConfigChange-class — logs every attempted control-file change |
| `hooks/registration/` | Hook registration snippets for Claude Code and GitHub Copilot |
| `managed-settings/templates/` | Org-level Claude Code managed settings + Copilot org-policy notes |
| `ci-checks/control-file-policy-check/` | CI: deny list covers every control glob; AGENTS.md ↔ CLAUDE.md shim intact |
| `lib/adlc_enforcement.py` | Shared stdlib helpers (glob matching, event normalisation, ledger append) |
| `tests/` | `python -m unittest discover -s skills/enforcement/tests` |

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `ADLC_CONTROL_PATHS` | `skills/governance/default-permissions/reference/control-file-paths.json` | guard, logger, CI |
| `ADLC_LEDGER_CLI` | `skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py` | fact-writer, logger |
| `ADLC_CHANGE_SET_ID` | unset | attached to FACT entries when set |
| `ADLC_FACT_MAX_CHARS` | `4000` | fact-writer content truncation (full output is hashed) |
| `CLAUDE_PROJECT_DIR` | hook `cwd` | repo root for path relativisation; `.adlc/` logs live here |

The hook passes `ADLC_HOOK_NAME=<hook>` in the ledger CLI's environment so the ledger can
derive `actor_id=hook:<hook>`, `actor_type=SYSTEM`.

## Failure posture

| Hook | On internal error | Why |
|---|---|---|
| control-file-guard | **fail closed** (exit 2) | A guard that fails open is not a guard |
| fact-writer | fail open, log to `.adlc/hook-errors.log` | Losing one FACT beats halting all work; the gap is visible |
| config-change-logger | fail open, log | Logging never blocks; blocking is the guard's job |

## Portability
Hook logic targets the common Claude Code / Copilot subset (`preToolUse`, `postToolUse`,
`sessionStart`, `sessionEnd`, `userPromptSubmitted`, `errorOccurred`). Extra Claude Code
events are enhancements, not dependencies (plan §8).
