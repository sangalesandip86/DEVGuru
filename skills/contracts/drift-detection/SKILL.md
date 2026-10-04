---
name: drift-detection
description: Compare declared contracts with observed reality and report drift. Use after deployments, in CI, or when production diverges from specs.
metadata:
  group: contracts
  phase: 3
  binding: false
  plan-ref: "§4.6, §6"
  stage: LEARN
  inputs: [contract]
  outputs: [incident]
  repo_roles: [contracts, app]
---

# Drift Detection


## Purpose
A registered contract is only useful while it matches reality. Drift detection finds where the
declared contract and the actual system have diverged, before a compatibility check passes on
evidence that no longer describes production.

## When this applies
- Scheduled CI run (recommended: daily, and after every deployment).
- A production incident involving an inter-service call.
- `dependency-discovery` finds an edge with no registered contract.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Runs at LEARN (scheduled) and on demand during REVIEW.

- **Inputs:** registered contracts and observed reality (provider code, traffic samples, deployed versions).
- **ADOPT:** contracts discovered in code but not registered are reported as drift, not silently registered.
- **Repo roles:** `contracts`, `app`.

## Procedure
1. `mcp:adlc.detect_drift` per contract (the contract_registry module of the adlc MCP server — plan's
   Server 3), comparing:
   - **Spec vs code:** routes/handlers and schemas found in the provider repo at the deployed SHA
     (`change-management/dependency-discovery/scripts/scan-api-calls.py` inbound routes) against the spec.
   - **Spec vs consumers:** outbound calls in consumer repos that hit operations or fields not in the spec.
   - **Registry vs deployments:** consumers calling the provider that are not listed in `consumers[]`.
   - **Spec vs traffic (if available):** observed requests/messages that fail schema validation.
2. Classify each finding: `UNDECLARED_OPERATION`, `UNDECLARED_CONSUMER`, `REMOVED_BUT_CALLED`,
   `SCHEMA_MISMATCH`, `STALE_SPEC_REF` (spec `content_hash` no longer matches `repo@sha:path`).
3. Static findings are `evidence_level: STATIC`; traffic findings are `OBSERVED` and outrank them.
4. Open a `RISK` entry per finding; drift on a contract in an active Change Set blocks it
   (`BLOCKED`) until reconciled.
5. Reconciliation is a normal change: update the spec or the code through a Change Set. Drift
   detection never edits specs or the registry itself.

## Outputs
- Drift report (JSON) as a `FACT` entry from CI.
- `RISK` entries per finding; incident records for drift that caused a production signal.

## Enforcement
**Guideline only** — no enforcement point yet.

Guideline only until the drift job runs as a scheduled CI workflow with its results ingested by the
server. Blocking an active Change Set on drift is enforced by the change_management module when the
drift `RISK` is linked to it.

## References
- [../contract-registry/reference/contract-schema.md](../contract-registry/reference/contract-schema.md)
- [../compatibility-check/SKILL.md](../compatibility-check/SKILL.md)
- [../../change-management/dependency-discovery/SKILL.md](../../change-management/dependency-discovery/SKILL.md)
