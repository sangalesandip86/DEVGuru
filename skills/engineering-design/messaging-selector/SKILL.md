---
name: messaging-selector
description: Select async messaging pattern and broker from throughput and delivery needs. Use when a design introduces events, queues, or jobs.
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

# Messaging Selector


## Purpose

Prevent both under-engineering (synchronous chains that fail under burst) and
over-engineering (a streaming platform for 50 messages/minute). Output is `REVIEWED`; never `VERIFIED`.

## When this applies

- New background job, event, webhook fan-out, or integration between services.
- Burst load that exceeds synchronous capacity.
- Proposal to introduce or replace a broker.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Primary stage ARCHITECTURE; also DESIGN when a story introduces a new channel.

- **Inputs:** throughput, ordering, delivery-guarantee and retention NFRs.
- **ASK:** missing numbers are batched into one QUESTION with proposed defaults.
- **Repo roles:** `planning` (ADR output).

## Existing project standards
On an existing repo, load [project-conventions](../project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- The project's existing technology is the default answer. Recommend a different one only when stated NFR numbers show the existing one can't meet them — cite the numbers and the evidence in the DECISION.

## Procedure

1. **First ask whether messaging is needed.** Synchronous call is preferred when the caller
   needs the result, volume is modest, and the callee's availability is acceptable. Record why
   async is required (burst smoothing, decoupled availability, fan-out, long-running work).
2. **Collect the numbers** per message flow: peak and sustained msgs/s, message size, ordering
   scope (none / per key / global), delivery semantics needed, replay/retention need, number of
   consumers, latency target. Missing → `QUESTION`.
3. **Select pattern and broker** via [`reference/decision-matrix.md`](reference/decision-matrix.md).
4. **Design for at-least-once by default:** idempotent consumers (idempotency key + dedup
   store), retries with backoff, dead-letter queue with an owner and alert.
5. **Treat the message schema as a contract** — register with `../../contracts/contract-registry/`
   (Phase 3); event contracts need compatibility checked in both directions.
6. Record a `DECISION` (`PROPOSED`) with matrix evidence.

## Outputs

- `DECISION` (pattern, broker, delivery semantics, ordering key, DLQ policy).
- `RISK` for each failure mode not handled (poison message, consumer lag, schema drift).
- `QUESTION` for missing numbers.

## Enforcement
**Guideline only** — no enforcement point yet.


- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Event-contract compatibility: `../../contracts/compatibility-check/` (Phase 3; until then, raise
  `COMPATIBILITY_UNKNOWN` → fail-safe INCOMPATIBLE per §5.3).
- Selection itself: **guideline only — no enforcement point yet**.

## References

- [`reference/decision-matrix.md`](reference/decision-matrix.md)
- `../system-architect/SKILL.md`, `../data-store-selector/SKILL.md`
