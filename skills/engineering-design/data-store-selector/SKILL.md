---
name: data-store-selector
description: Recommends a data store (relational, document, key-value, wide-column, search, time-series, graph, object storage) from stated access patterns, volume, consistency, and throughput numbers. Use when a Change Set introduces a new store, a new access pattern that strains the current one, or asks "which database should we use".
metadata:
  group: engineering-design
  phase: progressive
  binding: false
  plan-ref: "§4.9"
  stage: ARCHITECTURE
  inputs: [requirement, nfr-catalog]
  outputs: [adr]
  repo_roles: [planning]
---

# Data Store Selector

<!-- reconstructed: v2 source not provided; review -->

## Purpose

Make storage choices from access patterns and numbers rather than familiarity or fashion.
Output is a `REVIEWED` recommendation for the `architect` role; never `VERIFIED`.

## When this applies

- New persistent data in a new service or a new data shape.
- Proposal to add a second store (cache, search index, analytics store).
- Existing store showing a measured limit (latency, write throughput, storage cost).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Primary stage ARCHITECTURE; also DESIGN when a story introduces a new store.

- **Inputs:** data volumes, access patterns, consistency and retention NFRs.
- **ASK:** missing numbers are batched into one QUESTION with proposed defaults.
- **Repo roles:** `planning` (ADR output).

## Existing project standards
On an existing repo, load [project-conventions](../project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- The project's existing technology is the default answer. Recommend a different one only when stated NFR numbers show the existing one can't meet them — cite the numbers and the evidence in the DECISION.

## Procedure

1. **Write down access patterns first**, not entities: each query/write with frequency and
   latency target. Example: "get order by id — 3k/s, p99 20 ms"; "list orders by customer,
   newest first, paged — 400/s"; "monthly revenue by region — batch".
2. **Collect the numbers**: data volume now and in 24 months, read/write QPS, item size,
   consistency requirement (per pattern), retention, multi-region need. Missing number that
   affects the choice → `QUESTION`.
3. **Default to what is already operated.** A store the org already runs, backs up, and
   monitors wins ties. Adding a store has an ongoing operational cost — record it as a `RISK`.
4. **Score candidates** with [`reference/decision-matrix.md`](reference/decision-matrix.md).
   Eliminate on hard constraints first (consistency, transactions, compliance), then rank.
5. **Name the escape hatch**: what measured signal would make you migrate, and how hard is it.
6. Record a `DECISION` (`PROPOSED`) with the matrix as evidence; hand off to `system-architect`.

## Outputs

- `DECISION` with chosen store, rejected alternatives and why.
- `RISK` for operational cost of any new store; `QUESTION` for missing numbers.

## Enforcement

- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Introducing a store touching schema/migrations triggers the `*/migrations/` path tier
  (`../../change-management/risk-tiering/path-tiers.json`) and the always-overlap path classes
  in `../../change-management/snapshot/reference/staleness-policy.md`.
- Selection criteria themselves: **guideline only — no enforcement point yet**.

## References

- [`reference/decision-matrix.md`](reference/decision-matrix.md)
- `../system-architect/SKILL.md`, `../messaging-selector/SKILL.md`
