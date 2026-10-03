# Architecture templates

Used by [architecture-package](../../architecture-package/SKILL.md) for the ARCHITECTURE stage
(plan v3.1 §4.14). Copy each template into the planning repo's `architecture/` folder; the
target names are in the package skill. Example values describe a fictional payments system.
Replace them; never leave example numbers in a real package.

| Template | Target |
|---|---|
| current-state-architecture.md | `architecture/current-state.md` (brownfield) |
| standards-baseline.md | `architecture/standards-baseline.md` (greenfield) |
| solution-architecture.md | `architecture/README.md` |
| c4-context.md, c4-container.md | `architecture/c4/context.md`, `architecture/c4/containers.md` |
| adr-template.md | `architecture/adr/ADR-n-<slug>.md` (MADR) |
| nfr-tactics.yaml | `architecture/nfr-tactics.yaml` |
| integration-inventory.yaml | `architecture/integration-inventory.yaml` |
| data-model.md | `architecture/data-model.md` |
| threat-model.yaml | `architecture/threat-model.yaml` |
| deployment-view.md | `architecture/deployment.md` |
| risk-register.yaml | `architecture/risk-register.yaml` |
| service-map.yaml | `architecture/service-map.yaml` |
