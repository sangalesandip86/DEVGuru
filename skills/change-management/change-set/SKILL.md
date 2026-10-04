---
name: change-set
description: Define and manage Change Sets -- lifecycle, tasks, checkpoints, approvals. Use when creating, executing, resuming, or closing a unit of work.
metadata:
  group: change-management
  phase: 2
  binding: true
  plan-ref: "§4.5, §5.10"
  stage: IMPLEMENT
  inputs: [ready-story]
  outputs: [change-set]
  repo_roles: [app, planning]
---

# Change Set

## Purpose
The Change Set — not the repository — is the unit of orchestration (§1). It records what is being
changed, where, against which pinned snapshot, by which tasks, and which gates and approvals apply.

## When this applies
- **Single-repo work (Phase 1 default):** the issue + pull request on the forge *is* the Change
  Set. Do not call the change_management module of the adlc MCP server (plan's Server 2). State comes from forge events (§5.10): merge → `INTEGRATED`,
  deployment record + environment approval → `RELEASED`, CODEOWNERS review → human `APPROVED`.
- **Multi-repo or genuinely parallel work (Phase 2+):** create a Change Set through the
  change_management module of the adlc MCP server (plan's Server 2), `mcp:adlc.create_change_set`.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Change Sets start at IMPLEMENT and carry the work through TEST, REVIEW and INTEGRATE.

- **Inputs:** at least one READY story (`story_refs[]`); for HIGH+ tiers, the DESIGN-stage outputs.
- **ADOPT:** an existing open PR or branch for the story is adopted into a Change Set (single-repo: the issue + PR *is* the Change Set).
- **BACKFILL:** no READY story → propose `BACKFILL: PLAN` (refinement only). LOW-tier BUG_FIX/DOCUMENTATION may use an inline story in the PR body.
- **Dependency manifests:** any change to a dependency manifest (package.json, pom.xml, go.mod, pyproject.toml, etc.) must link a DECISION (plan §4.15); an unlinked manifest diff is flagged in CI.
- **Repo roles:** `app` (every repo the change touches — resolve or request creation first), `planning` (for `plans/stories/`).

## Procedure
1. Create the Change Set with requirement, repositories, contracts, environments, `parent_id`,
   `depends_on[]` ([changeset-schema.md](reference/changeset-schema.md)).
2. Pin a snapshot (`create_snapshot`) — commit SHAs, contract versions, environment state.
   "Latest" is never a reproducibility mechanism.
3. Compute the risk tier (`../risk-tiering/SKILL.md`); the tier selects gates (§5.4) and approvals
   ([approval-matrix.md](reference/approval-matrix.md)).
4. Plan `tasks[]` with dependencies and owner roles ([tasks-and-checkpoints.md](reference/tasks-and-checkpoints.md)).
5. Move through the lifecycle ([changeset-lifecycle.md](reference/changeset-lifecycle.md)). Agents
   may request `SCOPED`, `PLANNED`, `EXECUTING`, `VERIFYING`, `BLOCKED`. `PLAN_APPROVED`,
   `INTEGRATED`, `RELEASED` come only from authenticated human actions or forge events.
6. Checkpoint after each meaningful step; on crash or context pressure, resume per
   [resumability-rules.md](reference/resumability-rules.md).
7. Request integration only when [completion-criteria.md](reference/completion-criteria.md) all hold.

## Outputs
- Change Set record (adlc `change_management` module) or issue + PR (forge-native).
- `DECISION` entries for scope and plan; `QUESTION` entries (with `blocking` flag); `ASSUMPTION`
  entries with impact and expiry; handoffs via `record_handoff`.

## Enforcement
**Enforced** — see rules below.

- Agents cannot set `PLAN_APPROVED` / `INTEGRATED` / `RELEASED`: `update_status` rejects agent
  callers; only `ingest_forge_event` applies them (§5.6 row 1; adlc `change_management` module, plan's Server 2).
- Transition validity is enforced by the adlc `change_management` module's lifecycle table.
- Completion criteria are enforced by the adlc `change_management` module before accepting a merge-ready transition; in
  forge-native mode, by branch protection + required checks.

## References
- [changeset-schema.md](reference/changeset-schema.md) · [changeset.schema.json](reference/changeset.schema.json)
- [changeset-lifecycle.md](reference/changeset-lifecycle.md)
- [completion-criteria.md](reference/completion-criteria.md)
- [resumability-rules.md](reference/resumability-rules.md)
- [tasks-and-checkpoints.md](reference/tasks-and-checkpoints.md)
- [approval-matrix.md](reference/approval-matrix.md)
- [../snapshot/SKILL.md](../snapshot/SKILL.md) · [../risk-tiering/SKILL.md](../risk-tiering/SKILL.md)
  · [../parallel-execution/SKILL.md](../parallel-execution/SKILL.md)
- [../../roles/reference/handoff-schema.md](../../roles/reference/handoff-schema.md)
