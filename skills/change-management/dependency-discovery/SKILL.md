---
name: dependency-discovery
description: Discovers what a change depends on and what depends on it — imports, cross-repo packages, HTTP calls and routes — by static analysis, reporting anything unprovable as UNRESOLVED. Use when scoping a Change Set, when more than one repo may be involved, or before computing a risk tier.
metadata:
  group: change-management
  phase: 2
  binding: true
  plan-ref: "§4.5, §5.3"
  stage: IMPLEMENT
  inputs: [change-set]
  outputs: []
  repo_roles: [app, contracts]
---

# Dependency Discovery

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Find the repositories, packages, and services a change touches, using static analysis
(grep / import / call patterns) — not a declared-contract model; that comes in Phase 3 from the
patterns this skill surfaces.

## When this applies
- Scoping a Change Set (DRAFT → SCOPED).
- Any change to a shared library, public API, or service client.
- Before `compute_risk_tier` / the path lookup is finalized.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Primary stage IMPLEMENT; also used at PLAN by dependency-mapper and at ARCHITECTURE for the integration inventory.

- **Inputs:** the source trees of the repos in scope.
- **ASK:** if a dependency target resolves to a repo not in the workspace, raise one QUESTION listing candidate repos; until answered, the dependency is UNRESOLVED.
- **Repo roles:** `app` (scan targets), `contracts` (to match API calls against registered contracts).

## Procedure
1. Scan imports in each repository in scope:
   `python skills/change-management/dependency-discovery/scripts/scan-imports.py <repo-root> --known-repos known-repos.json`
   (`known-repos.json` maps package/module prefixes of in-scope repos to repo names.)
2. Scan HTTP calls and routes across all repos together, so cross-repo edges can be matched:
   `python .../scan-api-calls.py --repo web=../web --repo billing=../billing --known-hosts hosts.json`
3. For each `UNRESOLVED` entry: try one targeted search (grep for the symbol / host). If still
   unresolved, keep it `UNRESOLVED` — never downgrade it to "no dependency" (§5.3).
4. Record each dependency (`mcp:adlc.record_dependency`, or a ledger `FACT` in forge-native mode)
   with `evidence_level`: `STATIC` for these scans, `DECLARED` for manifest/contract declarations,
   `OBSERVED` for runtime traces.
5. Any `UNRESOLVED` edge that the change could plausibly affect → escalate the tier one level with
   reason code `UNRESOLVED_DEPENDENCY` (`../risk-tiering/reference/escalation-reason-codes.md`).
6. A newly discovered repository is added to the Change Set scope, and the snapshot is re-pinned.

## Outputs
- `FACT` entries: script output (source = command + file:line locations). Written by the
  fact-writer hook when the script runs through a hooked tool call.
- `INFERENCE` entries for any judgment that an edge is or is not affected.
- `RISK` entries for unresolved edges; Change Set `repositories[]` updates.

## Enforcement
Completion criterion 2 (no `UNRESOLVED` dependencies) is enforced by the change_management module
of the adlc MCP server (plan's Server 2) before `INTEGRATED`. In forge-native mode it is guideline
only unless the scan runs as a required CI check with `--fail-on-unresolved`.

## Scripts
| Script | Detects | Languages |
|---|---|---|
| [scripts/scan-imports.py](scripts/scan-imports.py) | imports → internal / stdlib / external (manifest-declared) / cross-repo / UNRESOLVED | Python, JS/TS, Java, Go |
| [scripts/scan-api-calls.py](scripts/scan-api-calls.py) | outbound HTTP calls + URL literals, inbound routes, cross-repo route matches | Python, JS/TS, Java/Kotlin, Go |

Both: stdlib only, JSON on stdout, exit 3 with `--fail-on-unresolved` when anything is unresolved.
Known limits: dynamic imports, reflection, DI containers, service discovery, and message queues are
not detected — these surface as `UNRESOLVED` or not at all, which is why runtime `OBSERVED`
evidence outranks `STATIC`.

Tests: `python -m unittest discover -s skills/change-management/dependency-discovery/tests`

## References
- [../change-set/SKILL.md](../change-set/SKILL.md)
- [../risk-tiering/SKILL.md](../risk-tiering/SKILL.md)
- [../../contracts/contract-registry/SKILL.md](../../contracts/contract-registry/SKILL.md)
