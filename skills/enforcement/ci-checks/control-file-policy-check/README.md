# control-file-policy-check

CI checks that the control-file protection is actually in place (plan §2 Phase 0: "CI checks
that verify those settings are actually in place"; §8 AGENTS.md shim check).

| Script | Fails when |
|---|---|
| `check_control_file_policy.py` | a control glob lacks `Edit(...)`/`Write(...)` deny rules; `allowManagedHooksOnly` not true; no PreToolUse guard; an allow rule re-opens a control path |
| `check_agents_md_shim.py` | an `AGENTS.md` lacks a sibling `CLAUDE.md` containing `@AGENTS.md` (`--strict`: nothing else) |
| `../../managed-settings/generate_deny_list.py --check` | the managed-settings template is stale vs `control-file-paths.json` |
| `flag_control_file_changes.py` | never fails — reports changed control files as CRITICAL in the job summary |

`workflow.example.yml` wires them into GitHub Actions. It lives here, not under
`.github/workflows/`, because each enrolled repo's copy is a control file that a human adds.

Point `--settings` at the settings file actually deployed to developer machines (exported
from MDM / server-managed settings) to check the real thing, not just the template.
