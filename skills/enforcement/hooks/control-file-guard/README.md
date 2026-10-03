# control-file-guard (PreToolUse)

Denies agent writes to platform control files — hooks, agent/skill/MCP config, `AGENTS.md`,
`CLAUDE.md`, `CODEOWNERS`, rulesets, CI workflows, and the platform `skills/` tree. Plan §4.1,
§4.11, §5.6 row "Control files are never agent-writable".

- Globs: `skills/governance/default-permissions/reference/control-file-paths.json`
  (override `ADLC_CONTROL_PATHS`).
- File tools checked: Claude Code `Edit`, `Write`, `MultiEdit`, `NotebookEdit`; Copilot
  `edit`, `create`, `str_replace*`, `insert`, `apply_patch`, `write_file`, `edit_file`.
- Shell tools checked (`Bash`, `shell`, `powershell`, …): only commands that look like writes
  (redirection, `tee`, `cp/mv/rm/touch`, `sed -i`, PowerShell `Set-Content`/`Out-File`/…,
  `git checkout/restore/apply`, inline `open(..., 'w')`). **Heuristic** — the managed-settings
  deny list and CODEOWNERS review are the layers that don't depend on parsing shell.
- Paths outside the repo are matched by suffix, so `~/.claude/settings.json` is protected too.

## Output
| Platform | Deny output |
|---|---|
| Claude Code | `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":…}}`, exit 0 |
| Copilot | `{"permissionDecision":"deny","permissionDecisionReason":…}`, exit 0 |
| Internal error | message on stderr, **exit 2** (fail closed) |

Denials are appended to `.adlc/control-file-guard.log`; the config-change-logger records the
attempt as a FACT.

## Manual test
```sh
echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":".claude/settings.json"},"cwd":"."}' \
  | python skills/enforcement/hooks/control-file-guard/control_file_guard.py
```
