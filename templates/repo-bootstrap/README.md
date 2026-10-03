# {{name}}

{{description}}

- **System:** `{{system}}`
- **Owning team:** `{{owner_team}}`

## Created by the ADLC platform

This repository was created from the platform template `templates/repo-bootstrap`, by a human or
an approved CI workflow, from a reviewed `repo-request.yaml`.

The template shipped these **control files**:
- `AGENTS.md` and its `CLAUDE.md` shim
- `CODEOWNERS`
- `.github/workflows/adlc-gates.yml`
- `.github/pull_request_template.md`

AI agents never write control files. Changes to them go through a human-approved PR, which
CODEOWNERS routes to the platform owners.

- `adlc.workspace.yaml` maps this system's repositories. It is a map, not a permission grant.
- `plans/` holds plan-as-code for single-repo work. See `plans/README.md`.
