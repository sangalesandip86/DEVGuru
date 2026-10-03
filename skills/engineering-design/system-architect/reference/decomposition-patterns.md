# Decomposition Patterns

<!-- reconstructed: v2 source not provided; review -->

Default: **don't split.** A module boundary inside one deployable gives most of the benefit of
a service boundary at a fraction of the operational cost. Split only when a specific force
below is evidenced.

## When a separate deployable is justified

| Force | Evidence required | Threshold heuristic |
|---|---|---|
| Independent scaling | Load profile per component | One component needs ≥5× the resources of the rest, or a different resource shape (GPU, memory-heavy) |
| Independent release cadence | Deploy logs, team structure | Teams blocked on each other's releases weekly or more |
| Fault isolation | Incident history | Failures in component A have taken down unrelated B in production |
| Different compliance scope | Compliance requirement | PCI/PHI data must be isolated from general workloads |
| Different team ownership | Org chart / CODEOWNERS | >1 team (≈ >8–10 engineers) regularly changing the same deployable |
| Technology mismatch | Requirement | Component needs a runtime the main stack cannot host |

None evidenced → recommend a module boundary and record a "Revisit when" trigger.

## Patterns

| Pattern | Use when | Avoid when | Key risk |
|---|---|---|---|
| **Modular monolith** | One team or a few; shared DB acceptable; <~10k QPS | Strong independent scaling need | Boundaries erode without enforcement (add import-lint rules) |
| **Decompose by business capability** | Stable domains (billing, catalog, identity) | Domain still being discovered | Wrong boundaries are expensive to move later |
| **Decompose by subdomain (DDD bounded contexts)** | Same term means different things in different areas | Small domain | Over-modeling |
| **Strangler fig** | Migrating a legacy system incrementally | Greenfield | Long dual-run period; routing complexity |
| **Database-per-service** | Services truly independent; different store needs | Cross-entity transactions are frequent | Distributed consistency (sagas/outbox) |
| **Shared database (transitional)** | Early split, migration underway | Long-term target | Hidden coupling via schema |
| **Backend-for-frontend** | Clients with very different needs (mobile vs web) | One client | Duplicated logic across BFFs |
| **Sidecar / service mesh** | Cross-cutting network concerns across many services | <5 services | Operational overhead |
| **Event-driven decoupling** | Consumers can tolerate eventual consistency | Caller needs synchronous answer | Debuggability; schema evolution (contracts) |

## Boundary checklist

- [ ] Each boundary owns its data; no other component writes to its tables.
- [ ] Every cross-boundary call is a contract with a named owner and compatibility direction.
- [ ] Synchronous call chains ≤ 3 hops on a user-facing path (each hop adds latency and failure probability).
- [ ] A chatty boundary (>~5 calls per user request) signals a misplaced boundary.
- [ ] Transactions that must span the boundary are listed, with the consistency mechanism (saga, outbox, 2PC-avoidance).
- [ ] Migration path from current state exists and is reversible at each step.

## Worked example

> Requirement: "Notifications are slow during campaign sends."
> Inputs: campaign burst 2M emails in 10 min (~3.3k/s), API p99 target 300 ms, one team.
> Finding: API and email sending share worker pool; burst starves API.
> Options: (a) separate worker pool + queue in the same deployable; (b) separate notification service.
> Decision: (a) — isolation of resources is the force, not team/release independence. Revisit when a second team owns notifications.
