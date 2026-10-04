---
name: snapshot
description: Pin commit SHAs and contract versions for a Change Set and detect staleness. Use before verification, resuming, or integration.
metadata:
  group: change-management
  phase: 2
  binding: true
  plan-ref: "§1, §4.5"
  stage: IMPLEMENT
  inputs: [change-set]
  outputs: []
  repo_roles: [app, contracts, infra]
---

# Snapshot

## Purpose
"Latest" is never a reproducibility mechanism (§1). A snapshot pins exactly what the Change Set was
analysed, implemented, and verified against, so every ledger entry can name its `snapshot_id`.

## When this applies
- Change Set creation (`DRAFT → SCOPED`).
- Before entering `VERIFYING`, before resuming from a checkpoint, before requesting integration.
- When a dependency scan adds a repository.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Snapshots are created when a Change Set enters IMPLEMENT and re-validated before VERIFYING.

- **Inputs:** the Change Set and the current HEAD of each resolved repo.
- **BLOCK:** if a repo in the Change Set can't be resolved to a commit SHA, the snapshot can't be pinned — never pin to "latest".
- **Repo roles:** every repo in the Change Set (`app`, plus `contracts`/`infra` when touched).

## Procedure
1. `mcp:adlc.create_snapshot` with, per repository, the base branch HEAD SHA; per contract, the
   registry version; per environment, the deployed version (`record_deployment` data, Phase 3).
   In forge-native mode, the PR's base SHA and head SHA are the snapshot.
2. Stamp `snapshot_id` on every ledger entry and task checkpoint made against it.
3. Check currency with `mcp:adlc.validate_snapshot_currency` at each trigger above. Apply
   [staleness-policy.md](reference/staleness-policy.md).
4. Stale → re-pin, then re-run the affected analysis (dependency scan, risk tier, compatibility
   check) and re-verify. Cached results keyed to the old `snapshot_id` are invalid.

## Outputs
- Snapshot record; `snapshot_id` on entries and checkpoints.
- `FACT` entry for each currency check result; `RISK` entry when stale.

## Enforcement
**Enforced** — see rules below.

The change_management module of the adlc MCP server (plan's Server 2) runs the staleness check
server-side. In forge-native mode, branch protection "require branches to be up to date" plus
required checks is the enforcement point.

## References
- [reference/staleness-policy.md](reference/staleness-policy.md)
- [../change-set/reference/resumability-rules.md](../change-set/reference/resumability-rules.md)
