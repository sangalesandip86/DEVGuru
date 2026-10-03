---
name: system-architect
description: Produces and reviews system-level design — service decomposition, boundaries, data ownership, and scaling approach — grounded in stated scale numbers. Use for HIGH/CRITICAL tier changes, new services, cross-repo Change Sets, or any "how should we structure / split / scale this system" question.
metadata:
  group: engineering-design
  phase: progressive
  binding: false
  plan-ref: "§4.9"
  stage: ARCHITECTURE
  inputs: [requirement, nfr-catalog]
  outputs: [architecture-package, adr]
  repo_roles: [app, planning, infra]
---

# System Architect

<!-- reconstructed: v2 source not provided; review -->

## Purpose

Support the `architect` role in making holistic design decisions that are grounded in
numbers — scale, QPS, data volume, latency targets, team structure — not generic
pattern-matching ("use microservices", "add Kafka"). Output is a judgment: `REVIEWED`, never `VERIFIED`.

## When this applies

- HIGH/CRITICAL tier gates require `architect` (§5.4).
- New service, new data store, new integration, or a boundary change between repos.
- Explicit request for an architecture decision or ADR.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Primary stage ARCHITECTURE; ARCHITECTURE-stage document assembly (C4 views, solution doc, NFR → tactic map, threat model, risk register, service/repo map) lives in [architecture-package](../architecture-package/SKILL.md) — this skill supplies the design reasoning it assembles.

- **Inputs:** requirements and the measurable NFR catalog from INTAKE.
- **ADOPT:** existing architecture docs/ADRs found by ingestion are imported as DRAFT with citations and reviewed, not regenerated.
- **BACKFILL:** no NFR catalog → propose `BACKFILL: INTAKE`; missing numbers (QPS, data volume, latency) become QUESTIONs.
- **Repo roles:** `planning` (where the package is written), `app`/`infra` (existing systems to read); the service/repo map it produces drives workspace creation.

## Existing project standards
On an existing repo, load [project-conventions](../project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Greenfield: establish the standards (ADRs plus lint and conformance configs) as part of the architecture package so later work has declared standards to follow.

## Procedure

1. **Collect the design inputs** into a table, each with a source:

   | Input | Value | Source |
   |---|---|---|
   | Peak QPS (read / write) | | |
   | Data volume now / in 12–24 months | | |
   | Latency target (p50 / p99) | | |
   | Availability target | | |
   | Consistency requirement | | |
   | Team(s) owning the result | | |
   | Existing constraints (cloud, language, compliance) | | |

   Any blank row that changes the recommendation → raise a `QUESTION` (blocking if the decision
   hinges on it). Do not fill it with a typical value; per `../../grounding/ambiguity-escalation/SKILL.md`
   an assumption must be tagged, impact-rated, and expiring.
2. **State the forces** — what makes this hard (e.g., "write rate 8k/s exceeds single-primary headroom of ~3k/s on current instance class").
3. **Generate 2–3 options**, always including "smallest change that works" (often: keep the monolith/module, add an index or cache).
4. **Evaluate options** against the inputs using
   [`reference/decomposition-patterns.md`](reference/decomposition-patterns.md) and
   [`reference/scaling-playbook.md`](reference/scaling-playbook.md). Delegate storage and messaging choices to
   `../data-store-selector/SKILL.md` and `../messaging-selector/SKILL.md`.
5. **Identify contract impact** — every new or changed boundary is a contract; note it for
   `../../contracts/contract-registry/` (Phase 3) or as a `RISK` if contracts aren't built yet.
6. **Write the ADR** (template below) and record a `DECISION` with `lifecycle_state: PROPOSED`.
7. **Hand off** to `developer` with the ADR as an `artifact_ref` (`repo@sha:path` + content hash).

### ADR template

```markdown
# AD-<n>: <title>
Status: PROPOSED   (REVIEWED by architect; APPROVED only by a human per approval-matrix)
Context: <forces, with numbers and sources>
Options: <2–3, each with cost, risk, reversibility>
Decision: <chosen option>
Consequences: <what gets easier/harder; contracts affected; migration steps>
Open questions: <QUESTION ids>
Revisit when: <measurable trigger, e.g. "write QPS > 5k sustained">
```

## Outputs

- `DECISION` (`REVIEWED`, ACCEPT/REJECT on a submitted design, or `PROPOSED` for its own).
- `RISK` entries for each unmitigated force; `QUESTION` for each missing input.
- ADR file as a handoff artifact.

## Enforcement

- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- `architect` cannot set `VERIFIED`/`APPROVED` — enforced by the MCP tool surface (§5.6 row 1).
- Architect may modify architecture docs only — enforced by role tool scoping
  (`../../governance/default-permissions/reference/role-tool-permissions.md`).
- "Ground in numbers" is **guideline only — no enforcement point yet**; human approvers should reject ADRs with empty input tables.

## References

- [`reference/decomposition-patterns.md`](reference/decomposition-patterns.md)
- [`reference/scaling-playbook.md`](reference/scaling-playbook.md)
- `../data-store-selector/SKILL.md`, `../messaging-selector/SKILL.md`, `../scale-readiness-reviewer/SKILL.md`
- `../../roles/architect/ROLE.md`
