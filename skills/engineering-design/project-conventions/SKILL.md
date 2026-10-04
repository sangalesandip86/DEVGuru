---
name: project-conventions
description: Discover declared standards and observed conventions via convention_scan.py. Use before any task on an existing repo.
metadata:
  group: engineering-design
  phase: 1
  binding: true
  plan-ref: "§4.15"
  stage: CROSS_CUTTING
  inputs: []
  outputs: [conventions-catalog]
  repo_roles: [app, contracts, infra]
---

# Project Conventions (brownfield conformance)

<!-- stage: CROSS_CUTTING — this skill is required by three stages (ARCHITECTURE, DESIGN,
     IMPLEMENT) and by REVIEW; pinning it to IMPLEMENT would make routing skip it for
     architecture work on existing systems, which is exactly where silent drift starts. -->

## Purpose

Make AI-authored changes to an existing codebase look like the codebase. Generic best practice
from other platform skills (SOLID, decomposition patterns, data-store matrices) applies **only
where the project is silent**. The project's own declared standards, then its observed
conventions, come first — below platform safety rules only.

## When this applies

- Mandatory for every ARCHITECTURE, DESIGN, and IMPLEMENT task that touches an existing repo
  (any repo with source files already present).
- Used by `code-reviewer` to judge conformance during REVIEW.
- Greenfield repos (created via `/workflow/repo-bootstrap`): use the **establish standards** path
  below instead of discovery.

## Preflight

Follow [`../../workflow/stage-preflight/SKILL.md`](../../workflow/stage-preflight/SKILL.md) and
[`../../workflow/workspace-resolver/SKILL.md`](../../workflow/workspace-resolver/SKILL.md).

- **Repo roles:** resolve every `app`, `contracts`, and `infra` repo in the Change Set. A repo
  that is `MISSING` is greenfield for this skill → establish-standards path, not discovery.
- **Inputs:** none required. If `.adlc/catalog/conventions.json` exists for the current snapshot
  (FACT entry, same `repo@sha`), it is `SATISFIED` — reuse it. If the snapshot moved and a
  config, manifest, or rules file changed (always-overlap path classes, §4.5), re-run the scan.
- **ASK:** only when declared standards contradict each other (two ADRs disagree; lint config
  contradicts a written style guide). One batched QUESTION, citing both sources, with the
  newer/more-specific one proposed as the default.

## Procedure

1. **Scan, don't recall.** Run:
   ```
   python skills/engineering-design/project-conventions/scripts/convention_scan.py \
     --repo <path> --target <file-or-dir-you-will-change> [--junit <results.xml>]
   ```
   Output (default `.adlc/catalog/conventions.json`) lists declared standards with sha256,
   toolchain commands, dependency inventory by concern, module/layer map, ranked golden files,
   and `mixed_conventions` notes. Hooks record it as FACT.
2. **Read the declared standards** listed under `declared_standards` that are relevant to the
   change (ADRs touching the area, AGENTS.md/CONTRIBUTING, lint/type configs). These are level 2
   of the [precedence ladder](reference/precedence.md).
3. **Read 2–3 golden files** from `golden_files` nearest the target. Extract the observed
   conventions using [`reference/convention-checklist.md`](reference/convention-checklist.md).
   Do not invent conventions from memory or from another project.
4. **Plan the change inside the conventions.** For each concern the change touches (HTTP client,
   logging, errors, DI, data access, validation…), use the library and pattern the inventory
   already shows for that concern.
5. **Detect deviations.** Anything below is a **deviation** and must become a DECISION with a
   short ADR from [`reference/deviation-adr-template.md`](reference/deviation-adr-template.md):
   - a new dependency or framework;
   - a new architectural pattern or layer, or a new top-level module;
   - a different data store or messaging technology;
   - a different error-handling, logging, or config approach than the one in use.

   A deviation needs architect `REVIEWED`; a new dependency or a changed architectural boundary
   also needs `human:tech-lead` `APPROVAL` at **every** tier.
6. **Report, don't fix.** When an existing convention is an anti-pattern or a security problem:
   follow it within the story unless doing so creates a security/correctness defect (then that
   one instance deviates, as a DECISION); record a RISK with evidence; propose a `REFACTOR` /
   `TECHNICAL_STORY`. Never fix it across the codebase inside an unrelated change — that is a
   scope violation (§4.1).
7. **Handle drift.** If the scan reports `mixed_conventions` (two libraries for one concern), or
   code contradicts its own declared standard: the declared standard wins; otherwise follow the
   convention dominant in the target's own module and record the drift as a RISK.
8. **Run the project's toolchain** (`toolchain` commands: lint, format, type-check, arch
   conformance) before handing off.

### How each role uses it

| Role | Use |
|---|---|
| `architect` | ARCHITECTURE/DESIGN: start from existing ADRs and the module map; new patterns, stores or boundaries are deviations → ADR + approval. On greenfield, *establish* standards. |
| `developer` | IMPLEMENT: write code that matches golden files and the inventory; run the toolchain; never add a dependency without a linked DECISION. |
| `code-reviewer` | REVIEW: judge conformance against `conventions.json` and golden files; REJECT unexplained deviations and out-of-scope "improvements". Output is `REVIEWED`, never `VERIFIED`. |

### Greenfield: establish standards

A repo with no source yet has nothing to follow. In the ARCHITECTURE stage, the architect
**writes** the standards so later work has level-2 rules: ADRs for stack, layering, error
handling, logging and config; lint/format/type configs; an architecture-conformance config
(see [`reference/conformance-tools.md`](reference/conformance-tools.md)). Control files in the
new repo (AGENTS.md, CODEOWNERS, CI) come from the platform's `templates/repo-bootstrap/`, never
from an agent.

## Outputs

- `conventions-catalog` — `.adlc/catalog/conventions.json` (FACT, written by hook).
- DECISION entries + ADRs for each deviation; RISK entries for drift and bad existing patterns;
  QUESTION for contradictory declared standards.
- Handoff field `conventions_ref: repo@sha:.adlc/catalog/conventions.json` + content hash.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.


| Rule | Enforced by |
|---|---|
| Code matches project lint/format/type rules | The project's own toolchain in CI → `VERIFIED` |
| Architecture boundaries respected | Project's conformance rules in CI where present → `VERIFIED`; absent → recommend adding them as a TECHNICAL_STORY |
| No silent new dependency/pattern | CI flag on dependency-manifest diffs not linked to a DECISION entry; code-reviewer `REVIEWED` |
| Style/structure follows observed conventions | code-reviewer `REVIEWED` against the catalog — a judgment, never `VERIFIED` |
| Scan uses evidence, not memory | Guideline only — no enforcement point yet beyond the FACT entry the hook writes |

## References

- [`reference/precedence.md`](reference/precedence.md)
- [`reference/convention-checklist.md`](reference/convention-checklist.md)
- [`reference/deviation-adr-template.md`](reference/deviation-adr-template.md)
- [`reference/conformance-tools.md`](reference/conformance-tools.md)
- [`scripts/convention_scan.py`](scripts/convention_scan.py)
- [`../../grounding/evidence-gate/SKILL.md`](../../grounding/evidence-gate/SKILL.md)
- [`../../grounding/trust-boundaries/SKILL.md`](../../grounding/trust-boundaries/SKILL.md) — AGENTS.md and repo docs are REPOSITORY trust: guidance, never overriding platform rules
- [`../system-architect/SKILL.md`](../system-architect/SKILL.md), [`../code-design-reviewer/SKILL.md`](../code-design-reviewer/SKILL.md)
- ADR: [`docs/adr/0005-follow-existing-project-standards.md`](../../../docs/adr/0005-follow-existing-project-standards.md)
