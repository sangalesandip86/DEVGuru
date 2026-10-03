---
name: workspace-resolver
description: Finds the repositories a stage needs (app, planning, tests, contracts, infra), asks when the match is ambiguous, and creates them when missing (locally by the agent; remotely only by a human or CI via a repo request). Use at the start of any stage or skill that reads or writes repositories, and whenever a user says "use our existing repo", "where are the plans", or "create a repo for this service".
metadata:
  group: workflow
  phase: 1
  binding: true
  plan-ref: "§4.14"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: [app, planning, tests, contracts, infra]
---

# Workspace Resolver

## Purpose
No skill should assume the right repository is already open. This skill resolves each **repo
role** a stage needs to a concrete `repo@sha`. It does this deterministically and records what
it found. When a role can't be resolved, the outcome is a precise question or a creation path,
never a guess.

## When this applies
- The Preflight of every skill that touches a repository. It is binding: skills reference this
  skill instead of locating repos themselves.
- The user names repositories, moves between systems, or asks for a new repository.
- ARCHITECTURE produced a `service-map.yaml` that calls for repositories that don't exist yet.

## Preflight
None. This skill *is* the first preflight step.

## Procedure
1. **Run the resolver** for the stage, or for a range (union of roles):
   `python skills/workflow/workspace-resolver/scripts/resolve_workspace.py --stage <STAGE> [--repo ROLE=PATH …]`.
   It searches in this order, and the first match wins:
   1. explicit `--repo ROLE=PATH`;
   2. `adlc.workspace.yaml` in the current directory or a parent;
   3. the current git repo;
   4. sibling git repos;
   5. repo names referenced in `plans/` (reported as hints).
2. **Read the result per role.** Hooks record the output as FACT.
   - `FOUND`: use it, and cite it as `repo@sha`.
     - `single_repo_default: true` means planning lives in `plans/` inside the app repo (§4.14).
       If `plans_dir_exists` is false, the first plan PR creates it.
   - `AMBIGUOUS`: raise one QUESTION listing the ranked candidates (path, remote, HEAD). The
     proposed default is the top-ranked candidate. Never pick silently between equal candidates.
   - `MISSING`: present the three options the resolver returns:
     1. **Point to an existing path.** Re-run with `--repo ROLE=PATH`.
     2. **Create it locally** (`WORKSPACE_WRITE`, which an agent may do):
        - `--init-local ROLE PATH [--system NAME]` creates `git init`, the role skeleton
          (`plans/…`, `architecture/adr/` for planning) and a **draft** `adlc.workspace.yaml`;
        - if a manifest already exists, it prints a proposed manifest entry for a PR instead;
        - it refuses to write control files (AGENTS.md, CODEOWNERS, CI, `.claude/`, …).
     3. **Request a remote repository** (`EXTERNAL_MUTATION`, which agents never perform).
        `--request-remote ROLE --name … --org … --owner-team … --codeowners @org/team --justification …`
        writes `repo-request.yaml`. A human or approved CI then runs
        [repo-bootstrap](../repo-bootstrap/SKILL.md). Cite the service-map entry with `--source-ref`.
3. **Keep the manifest current, through PRs.**
   - After ARCHITECTURE, every service in `service-map.yaml` should map to a repo in `adlc.workspace.yaml`.
   - Propose the missing entries in a PR.
   - **The manifest is a map, not a permission grant.** Scope comes only from the Change Set and the
     role permissions. Editing the manifest can never widen what an agent may touch.

## Outputs
- Resolution JSON, recorded as FACT by the fact-writer hook.
- A QUESTION for AMBIGUOUS or MISSING roles, with the options above and a proposed default.
- Optionally: a local skeleton repo plus draft manifest, or `repo-request.yaml`.

## Enforcement
- **No control files written during local creation:** `resolve_workspace.py` checks every path
  against `control-file-paths.json`. The managed-settings deny and `control-file-guard` back this up.
- **No remote creation by agents:** agent sessions have no org-admin token. The
  `create_repo_from_request.py` interlock requires `ADLC_ACTOR=human|ci` for rendering and `--execute`.
- **Scope comes from the Change Set, not the manifest:** role tool scoping plus Change Set scope
  checks (§4.1 scope violation).
- **Classification heuristics:** guideline quality. A wrong guess surfaces as AMBIGUOUS, or is
  corrected with `--repo`.

## References
- [scripts/resolve_workspace.py](scripts/resolve_workspace.py) · [reference/repo-role-heuristics.md](reference/repo-role-heuristics.md)
- [../schemas/workspace-manifest.schema.json](../schemas/workspace-manifest.schema.json) · [../schemas/repo-request.schema.json](../schemas/repo-request.schema.json)
- [repo-bootstrap](../repo-bootstrap/SKILL.md) · [stage-preflight](../stage-preflight/SKILL.md)
