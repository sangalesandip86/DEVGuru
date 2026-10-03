---
name: pact-consumer-driven
description: Implements consumer-driven contract tests with Pact (HTTP and message pacts), publishing to a Pact Broker and gating deploys with can-i-deploy against recorded deployed versions. Use when a Change Set changes an API or event that another service consumes.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8, §4.6"
  stage: TEST
  inputs: [contract, test-design]
  outputs: [test-suite]
  repo_roles: [app, contracts]
---

# Pact Consumer-Driven Contracts

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Prove that a provider change won't break the consumers that are *actually deployed*, without
standing up the whole system.

## When this applies
- A Change Set modifies a request/response shape, status codes, or an event payload crossing a service boundary.
- Risk tier is HIGH (public API change — plan §5.4 requires contract analysis).

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, contracts]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Contract and broker.** The provider/consumer pair is registered in the contract registry, and a Pact Broker (or PactFlow) is reachable from CI. can-i-deploy runs against **recorded deployed versions**, not the latest ones.

Never proceed on a missing input silently.

## Procedure
1. **Consumer side** — write the pact from the consumer's real usage, only the fields it reads:
   ```ts
   await provider
     .given('order 42 exists')
     .uponReceiving('a request for order 42')
     .withRequest({ method: 'GET', path: '/orders/42' })
     .willRespondWith({ status: 200, body: { id: like(42), total: decimal(19.99), status: regex('PAID|PENDING', 'PAID') } })
     .executeTest(async (mock) => { await new OrdersClient(mock.url).get(42); });
   ```
   Use matchers (`like`, `eachLike`, `regex`), not literal values, so the contract states shape, not data.
2. **Publish** with the consumer's git SHA as the version and branch metadata:
   `pact-broker publish ./pacts --consumer-app-version $GIT_SHA --branch $BRANCH`.
3. **Provider verification** in provider CI, against pacts selected by
   `{ mainBranch: true }, { deployedOrReleased: true }`, with provider states implemented as real setup hooks.
   Enable pending pacts and WIP pacts so a new consumer expectation doesn't break the provider build before it is agreed.
4. **Record deployments**: CI runs `pact-broker record-deployment --pacticipant <app> --version $GIT_SHA --environment <env>`
   after each deploy. This mirrors the platform's `record_deployment` tool (Contract Registry, plan §6 Server 3).
5. **Gate**: before deploy, `pact-broker can-i-deploy --pacticipant <app> --version $GIT_SHA --to-environment <env>`
   — or the platform's `compatibility-check/scripts/check-can-i-deploy.py`. Unknown compatibility is
   `INCOMPATIBLE` by default (plan §5.3).
6. For events, use message pacts and verify **both directions** (old producer → new consumer,
   new producer → old consumer) as `compatibility-check` requires.

## Outputs
- Pact files (`REPO_WRITE`). Provider verification and can-i-deploy results → server sets `VERIFIED`.
- A missing pact for a known consumer → `RISK` + `COMPATIBILITY_UNKNOWN` reason code (escalates the tier by one).

## Enforcement
can-i-deploy is a deterministic CI gate; its result is machine evidence. Writing pacts is guideline only.

## References
- [`../../../contracts/compatibility-check/`](../../../contracts/compatibility-check/)
- [`../schema-validation/SKILL.md`](../schema-validation/SKILL.md)
- [`../../../change-management/risk-tiering/`](../../../change-management/risk-tiering/)
