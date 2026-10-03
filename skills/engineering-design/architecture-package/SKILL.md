---
name: architecture-package
description: Drives the ARCHITECTURE stage. It assembles the solution-level document set (current-state or standards baseline, C4 context/container views, solution architecture doc, ADRs, NFR-to-tactic mapping, integration/contract inventory, data model, STRIDE threat model, deployment view, risk register, service/repo map) from the INTAKE outputs, grounded in measurable NFRs. For existing systems it produces a delta against the current architecture. Use after requirements are ingested and before epics and stories are planned.
metadata:
  group: engineering-design
  phase: 1
  binding: false
  plan-ref: "§4.14, §4.15"
  stage: ARCHITECTURE
  inputs: [requirement, nfr-catalog, conventions-catalog]
  outputs: [architecture-package, adr, contract]
  repo_roles: [planning, app, contracts, infra]
---

# Architecture Package (ARCHITECTURE stage)

## Purpose
Architecture comes **before** planning. Service boundaries, contracts and repositories decide how
epics and stories should be cut (§4.14). This skill produces one reviewable package in the
planning repo's `architecture/` folder. Every choice in it traces to a requirement, an NFR with a
number, or a constraint. The package also yields the **service/repo map** that workspace
resolution and repo creation use.

The architecture **judgment** belongs to the `architect` role, through
[system-architect](../system-architect/SKILL.md),
[data-store-selector](../data-store-selector/SKILL.md) and
[messaging-selector](../messaging-selector/SKILL.md). This skill defines *what the package must
contain* and *how brownfield and greenfield differ*. Its output is **REVIEWED**, never VERIFIED.

## When this applies
- An `/adlc` run reaches ARCHITECTURE, typically after [requirements-ingestion](../../workflow/requirements-ingestion/SKILL.md).
- PLAN preflight returned `BACKFILL → ARCHITECTURE`: tier MEDIUM or above with no package.
- A new requirement changes boundaries, data ownership, integrations or NFR targets of an existing system.

## Preflight
- [workspace-resolver](../../workflow/workspace-resolver/SKILL.md): `planning` is required, and `app`, `contracts` and `infra` are optional.
- [stage-preflight](../../workflow/stage-preflight/SKILL.md) `--start ARCHITECTURE`:
  - `requirement` and `nfr-catalog` must be SATISFIED. BACKFILL means INTAKE comes first.
  - **Existing system:** `conventions-catalog` must be fresh. BACKFILL means run `convention_scan.py`.
  - The current-state package is optional, and adopted when supplied.
- Unquantified NFRs (an `open_question` with no target) are listed. Decisions that depend on them
  wait, or proceed on an expiring ASSUMPTION per the ask-vs-assume matrix. Never on an invented number.

## Procedure
### 1. Decide brownfield or greenfield
| | Brownfield (the system or app repo already exists) | Greenfield |
|---|---|---|
| Starting point | **Current state**: ingest existing ADRs, diagrams and docs ([brownfield-adoption](../../workflow/brownfield-adoption/SKILL.md) B), plus `conventions.json` for each repo | Requirements and NFRs only |
| First document | `current-state.md` ([template](../system-architect/templates/current-state-architecture.md)) | `standards-baseline.md` ([template](../system-architect/templates/standards-baseline.md)) |
| Existing decisions | **Inputs, not things to redesign.** Changing one means a new ADR that *supersedes* it, plus `human:tech-lead` APPROVAL at any tier | — |
| Output | A **delta**: what is added or changed, with everything else explicitly unchanged | The full package, **establishing standards**: ADRs for stack, layering, error handling, logging and config, plus lint, format, type and architecture-conformance configs for the repos |
| Precedence | Platform rules, then declared standards, then observed conventions, then generic guidance (§4.15) | Generic guidance, which becomes the declared standards |

### 2. Assemble the package
Write to `architecture/` in the planning repo through a PR. Every section cites
`source_refs` (REQ, NFR, CON ids, document anchors, `repo@sha:path`).

| File | Template | Must contain |
|---|---|---|
| `architecture/README.md` | [solution-architecture.md](../system-architect/templates/solution-architecture.md) | Context, goals, the chosen approach with the alternatives considered, the delta (brownfield), and links to every other file |
| `architecture/current-state.md` *or* `architecture/standards-baseline.md` | as above | See step 1 |
| `architecture/c4/context.md`, `architecture/c4/containers.md` | [c4-context.md](../system-architect/templates/c4-context.md), [c4-container.md](../system-architect/templates/c4-container.md) | Mermaid C4 (Structurizr DSL optional). Every external system and container is named the same way as in the service map. |
| `architecture/adr/ADR-n-<slug>.md` | [adr-template.md](../system-architect/templates/adr-template.md) (MADR) | One per significant decision. `Supersedes:` and `Superseded-by:` links. Status: proposed or accepted, where accepted means after APPROVAL. |
| `architecture/nfr-tactics.yaml` | [nfr-tactics.yaml](../system-architect/templates/nfr-tactics.yaml) | **Every MUST NFR** maps to tactics, plus the verification that will prove it (load test, chaos test, SLO alert) |
| `architecture/integration-inventory.yaml` | [integration-inventory.yaml](../system-architect/templates/integration-inventory.yaml) | Each integration: direction, protocol, contract reference, owner, failure mode, and compatibility policy (feeds `/contracts`) |
| `architecture/data-model.md` | [data-model.md](../system-architect/templates/data-model.md) | Entities from the glossary, ownership per service, classification (PUBLIC to RESTRICTED), retention per constraint |
| `architecture/threat-model.yaml` | [threat-model.yaml](../system-architect/templates/threat-model.yaml) | STRIDE per trust boundary or data flow, with a mitigation per threat, owner and status. Unmitigated HIGH threats become RISK entries. |
| `architecture/deployment.md` | [deployment-view.md](../system-architect/templates/deployment-view.md) | Environments, regions (with data residency per constraint), scaling unit, rollout strategy |
| `architecture/risk-register.yaml` | [risk-register.yaml](../system-architect/templates/risk-register.yaml) | Mirrors the RISK ledger entries, with likelihood, impact, owner and mitigation |
| `architecture/service-map.yaml` | [service-map.yaml](../system-architect/templates/service-map.yaml) | Service → repo → owner team → contracts. **This feeds `adlc.workspace.yaml`**, and new repos follow from [repo-bootstrap](../../workflow/repo-bootstrap/SKILL.md). |

### 3. Ground every choice in numbers
Each tactic or technology choice states the NFR number it serves. "Kafka because 20k events/s
at peak with 7-day replay (NFR-6)" is acceptable. "Kafka for scalability" is not. Missing numbers
become QUESTIONs ([evidence-gate](../../grounding/evidence-gate/SKILL.md)).

### 4. Deviations and new dependencies (brownfield)
Each of these is a **DECISION with an ADR**, needs architect REVIEWED, and needs `human:tech-lead`
APPROVAL at any tier (§4.15):
- a new framework or library for a concern the repo already covers;
- a new data store or messaging technology;
- a new layer or a boundary change.

A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR or
TECHNICAL_STORY. It is never redesigned in passing.

### 5. Hand off
- Get architect REVIEWED/ACCEPT on the package. In degraded mode, `human:tech-lead` stands in.
- Get `human:tech-lead` APPROVAL for HIGH+ systems and for any superseding ADR. The exit gate is
  in `stages.yaml → ARCHITECTURE`.
- Propose manifest entries from `service-map.yaml`. For each service without a repo, the resolver
  offers `--request-remote`.
- Hand off to PLAN. [epic-decomposer](../../product-planning/epic-decomposer/SKILL.md) cuts epics
  along the service boundaries.

## Outputs
- The `architecture/` document set through a PR.
- Ledger entries: DECISION (one per ADR), RISK (threats, risks, drift), QUESTION (missing
  numbers), and a handoff to PLAN.

## Enforcement
- **Exit gate:**
  - the review must come from architect REVIEWED/ACCEPT, or a human; SYSTEM evidence never counts;
  - for HIGH+ systems and any superseding ADR, an authenticated `human:tech-lead` APPROVAL is also required.

  Both are checked by `stage_preflight.py` when PLAN starts. The approval is enforced by the forge
  through CODEOWNERS on `docs/adr/` and `architecture/adr/` in repos created from `templates/repo-bootstrap`.
- **New dependencies need a DECISION:** `dependency-decision-check` in CI plus CODEOWNERS routing of
  dependency manifests to the tech lead.
- **Conformance to declared standards:** the project's own linters and conformance tools in CI
  (VERIFIED), plus code-reviewer REVIEWED.
- **Package quality (grounding, completeness):** REVIEWED judgment. Guideline-level beyond the gate.

## References
- Templates: [../system-architect/templates/](../system-architect/templates/) · [reference/document-set.md](reference/document-set.md)
- [system-architect](../system-architect/SKILL.md) · [project-conventions](../project-conventions/SKILL.md) · [data-store-selector](../data-store-selector/SKILL.md) · [messaging-selector](../messaging-selector/SKILL.md)
- [workflow/stages.yaml](../../workflow/stages.yaml) · [requirements-ingestion](../../workflow/requirements-ingestion/SKILL.md) · [brownfield-adoption](../../workflow/brownfield-adoption/SKILL.md)
