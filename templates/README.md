# Platform templates

Templates here are **platform-owned**. They are rendered only by
[`create_repo_from_request.py`](../skills/workflow/repo-bootstrap/scripts/create_repo_from_request.py),
run by a **human or an approved CI workflow**, never by an agent (plan v3.1 §4.14, ADR 0004).

| Template | Used for |
|---|---|
| [`repo-bootstrap/`](repo-bootstrap/) | A new repository, created from a reviewed `repo-request.yaml` |

`repo-bootstrap/` ships the files that are **control files** in every product repo:
- `AGENTS.md`, plus a `CLAUDE.md` shim containing `@AGENTS.md`
- `CODEOWNERS`
- `.github/workflows/adlc-gates.yml`

Agents must never author those files (plan §4.1 control-files), so they reach a new
repository only through this template.

Placeholders use `{{name}}`. They are filled from the request fields:
- `org`, `name`, `system`, `description`
- `owner_team`, `default_branch`
- `codeowners_owner`, `tech_lead_owner`, `platform_owner`
- `platform_repo`, `platform_sha`

An owner the request doesn't set stays as a visible `@<…-team>` placeholder. `--execute` then
refuses to run until a human fills it in.
