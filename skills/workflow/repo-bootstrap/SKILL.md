---
name: repo-bootstrap
description: Create a new repository from a reviewed repo-request.yaml using the platform template. Use when a role is MISSING and a new repo is needed.
metadata:
  group: workflow
  phase: 1
  binding: false
  plan-ref: "§4.14"
  stage: CROSS_CUTTING
  inputs: [architecture-package]
  outputs: []
  repo_roles: [planning]
---

# Repo Bootstrap

## Purpose
A new repository needs the platform's control files from day one, and **agents must never
author control files** (§4.1). Creating a remote repository is also `EXTERNAL_MUTATION`, which
agents never perform (§4.5, §5.9). This skill splits the job:

| Step | Who |
|---|---|
| Draft `repo-request.yaml` (name, org, owners, visibility, branch protection, justification) | Agent: `resolve_workspace.py --request-remote` |
| Preview the files and commands | Anyone: the default mode of `create_repo_from_request.py` |
| Render `templates/repo-bootstrap` (it contains control files) | Human or CI: `ADLC_ACTOR=human\|ci` |
| Run `git` / `gh repo create` / branch protection | Human or CI: `--execute` |

## When this applies
- The [workspace-resolver](../workspace-resolver/SKILL.md) reports a role `MISSING`, and the user wants a remote repo rather than a local one.
- ARCHITECTURE's `service-map.yaml` names a service whose repository doesn't exist yet.

## Preflight
- The request should trace to a reason: a service-map entry (`--source-ref`) or a user statement.
- For a new service, the ARCHITECTURE stage's package should be REVIEWED. A repository is a boundary decision.

## Procedure
1. **Draft the request** with `resolve_workspace.py --request-remote <role> --name … --org … --owner-team …
   --codeowners @org/team --requested-by agent:<role> --justification "…" --source-ref <service-map ref>`.
   - Add `tech_lead_owner` and `platform_owner` to the YAML if you know them.
   - If you don't, the rendered CODEOWNERS keeps a visible `@<tech-lead-team>` or `@<platform-team>`
     placeholder, and `--execute` refuses to run.
2. **Open a PR** with `repo-request.yaml` in the planning repo. The request itself is reviewable
   evidence.
3. **Preview.** `python skills/workflow/repo-bootstrap/scripts/create_repo_from_request.py repo-request.yaml --target ../<name>`
   lists every file the template will render, plus the exact commands. Include this output in the PR description.
4. **A human or CI executes it** with `ADLC_ACTOR=human` or `ADLC_ACTOR=ci`, plus `--execute`,
   `--platform-repo <org>/adlc-platform` and `--platform-sha <pinned sha>`. Never "latest".
5. **After creation:**
   - The workspace manifest gets the new repo through a PR. The resolver proposes the entry.
   - Re-run the resolver. The role is now FOUND.

## What the template ships
- **`AGENTS.md` and a `CLAUDE.md` shim** (`@AGENTS.md`), satisfying the §8 shim CI check.
- **`CODEOWNERS`:**
  - default owners;
  - **dependency manifests** (`package.json`, `pyproject.toml`, `requirements*.txt`, `pom.xml`,
    `build.gradle*`, `go.mod`, `Cargo.toml`, `pubspec.yaml`, `*.csproj`) **and `docs/adr/`** route
    to the tech lead, so `human:tech-lead` APPROVAL for new dependencies and boundaries (§4.15,
    ADR 0005) is enforced by the forge;
  - control files route to the platform owners.
- **`.github/workflows/adlc-gates.yml`**, pinned to a platform SHA:
  - control-file change flagging;
  - the AGENTS.md shim check;
  - **dependency-decision-check**;
  - plan-lint.
- **`.github/pull_request_template.md`** with `Implements: ST-n`.
- **`plans/README.md`**, a draft **`adlc.workspace.yaml`**, and a `.gitignore` covering `.adlc/` and common secret files.
- **Branch protection:** required reviews, CODEOWNERS review, required status checks and stale-review dismissal.

## Outputs
- `repo-request.yaml` (agent), the preview JSON, and, run by a human or CI, the new repository.
- Ledger entries: a DECISION for the new repo, with the service-map reference. The created
  repository is observed as a SYSTEM FACT.

## Enforcement
**Enforced** (partial) — see rules below.

- **Agents can't create remote repos:** they hold no org-admin token, `--execute` requires
  `ADLC_ACTOR=human|ci`, and the operation class is CI/server only.
- **Agents can't write the template's control files:** rendering requires `ADLC_ACTOR=human|ci`,
  backed by the managed-settings deny and `control-file-guard` for agent sessions. `ADLC_ACTOR` is
  an interlock, **not** a security boundary.
- **Unfilled owners or unpinned platform:** `--execute` refuses.
- **The PR review of the request** is human.

## References
- [scripts/create_repo_from_request.py](scripts/create_repo_from_request.py) · [templates/repo-bootstrap](../../../templates/repo-bootstrap/)
- [../schemas/repo-request.schema.json](../schemas/repo-request.schema.json) · [workspace-resolver](../workspace-resolver/SKILL.md)
- [dependency-decision-check](../../enforcement/ci-checks/dependency-decision-check/README.md) · [control-file policy](../../governance/default-permissions/reference/control-file-policy.md)
