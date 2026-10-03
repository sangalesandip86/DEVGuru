# Managed settings

Control-file protection must live at the **organization** layer. A project-local
`.claude/settings.json` can be rewritten by anyone with repo write access, or by an injected
agent with shell access — that's a suggestion, not a control (plan §4.1).

## Claude Code
`templates/claude-code-managed-settings.json` is **generated** — run
`python generate_deny_list.py` after editing `control-file-paths.json`, and
`--check` in CI.

| Key | Purpose |
|---|---|
| `permissions.deny` | `Edit(<glob>)` + `Write(<glob>)` for every control-file glob |
| `permissions.disableBypassPermissionsMode` | Agents can't be launched in a mode that skips the deny list |
| `allowManagedHooksOnly` | Only org-managed hooks run; a repo can't add or shadow hooks |
| `allowManagedPermissionRulesOnly` | Repo/user settings can't add allow rules that override the deny list |
| `hooks` | control-file-guard, config-change-logger, fact-writer (from `../hooks/registration/`) |

Deploy to the OS managed-settings path (admin-owned, e.g. `/etc/claude-code/managed-settings.json`,
`/Library/Application Support/ClaudeCode/managed-settings.json`,
`C:\Program Files\ClaudeCode\managed-settings.json`) or via your MDM / server-managed
settings. Check key names against the current Claude Code settings reference before rollout —
keys this template relies on must exist in the version you deploy.

## GitHub Copilot
Copilot has no equivalent of a local managed-settings deny list. The equivalent controls are:
see [templates/copilot-org-controls.md](templates/copilot-org-controls.md).
