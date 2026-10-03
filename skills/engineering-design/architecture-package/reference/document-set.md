# Architecture package: completeness checklist

The architect uses this list before requesting review, and the reviewer checks it. Every item
needs a `source_ref`, or it becomes a QUESTION.

## Always
- [ ] `README.md` names the goals (REQ ids), the chosen approach, **at least one rejected
      alternative with the reason**, and links every file.
- [ ] C4 context: every external actor and system from the personas and integrations appears.
- [ ] C4 containers: every deployable unit appears **with the same name as in `service-map.yaml`**.
- [ ] Every MUST NFR has a row in `nfr-tactics.yaml` with a tactic **and** a verification method.
- [ ] Every integration in `integration-inventory.yaml` has an owner, protocol, contract reference
      (or "to be defined", which creates a QUESTION) and failure mode.
- [ ] `data-model.md`: each entity has one owning service and a data classification.
      CONFIDENTIAL or RESTRICTED data shows retention and residency per constraint.
- [ ] `threat-model.yaml`: every trust boundary crossing in the container view has STRIDE entries.
- [ ] `deployment.md`: environments, rollout strategy (staged for CRITICAL), and data residency per region.
- [ ] `risk-register.yaml` mirrors open RISK entries.
- [ ] `service-map.yaml`: every service has `repo`, `owner_team` and `contracts`. New repos are listed with `exists: false`.

## Brownfield only
- [ ] `current-state.md` lists existing ADRs as `repo@sha:path` and is unchanged except for additions.
- [ ] The delta section says explicitly what is **unchanged**.
- [ ] Each changed decision has a **new** ADR with `Supersedes: ADR-n`, plus a `human:tech-lead` APPROVAL request.
- [ ] Each new dependency, data store or messaging technology has an ADR. Drift from declared
      standards is a RISK, not a fix.
- [ ] Conventions catalog references are used for the module, layer and library names in the delta.

## Greenfield only
- [ ] `standards-baseline.md` covers language/runtime, layering, error handling, logging and
      telemetry, config and secrets, testing tiers, and API style. Each item has an ADR.
- [ ] Lint, format, type and architecture-conformance tools are chosen, and their config files are
      listed for each repo's first story (TEST_AUTOMATION or INFRASTRUCTURE type).
