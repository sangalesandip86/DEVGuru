# Solution architecture: <system / initiative>

<!-- architecture/README.md. Every section cites REQ / NFR / CON ids or document anchors. Missing
     numbers become QUESTIONs, never invented. Output is REVIEWED by the architect; HIGH+ systems
     and superseding ADRs also need human:tech-lead APPROVAL. -->

## 1. Context and goals
- Requirements in scope: REQ-…
- Outcomes: … (from REQ `business_outcome`)
- Constraints: CON-… (regulatory, residency, contractual)

## 2. Starting point
- Brownfield: see [current-state.md](current-state.md). **Delta only** below.
- Greenfield: see [standards-baseline.md](standards-baseline.md).

## 3. Approach
<!-- The chosen design in 5–10 sentences, tied to the NFR numbers it serves. -->

### Alternatives considered
| Option | Why not chosen (with numbers) |
|---|---|

## 4. Delta (brownfield)
| Area | Change | Explicitly unchanged | ADR |
|---|---|---|---|

## 5. Views
- [C4 context](c4/context.md) · [C4 containers](c4/containers.md) · [Deployment](deployment.md) · [Data model](data-model.md)

## 6. Quality attributes
See [nfr-tactics.yaml](nfr-tactics.yaml). Every MUST NFR maps to a tactic and its verification.

## 7. Integrations and contracts
See [integration-inventory.yaml](integration-inventory.yaml).

## 8. Security
See [threat-model.yaml](threat-model.yaml).

## 9. Risks and open questions
See [risk-register.yaml](risk-register.yaml). Open QUESTIONs: ENTRY-…

## 10. Service/repo map
See [service-map.yaml](service-map.yaml). It feeds `adlc.workspace.yaml`; new repos go through `repo-request.yaml`.
