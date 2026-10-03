# Hook registration

| File | Platform | Install location |
|---|---|---|
| `claude-code-hooks.json` | Claude Code | merged into the **managed** settings file (see `../../managed-settings/templates/`) |
| `copilot-hooks.json` | GitHub Copilot | `.github/hooks/hooks.json`, protected by CODEOWNERS + ruleset |

Replace `{{ADLC_ENFORCEMENT_DIR}}` with the absolute path where the org installs
`skills/enforcement/` (a read-only, admin-owned location — e.g. `/opt/adlc/enforcement` or
`C:\ProgramData\adlc\enforcement`). Never point it at a path inside the working repo.

Order matters only for readability: the logger is listed before the guard so attempts are
logged even when the guard denies.
