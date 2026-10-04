---
name: schema-validation
description: Validate APIs against declared schemas (OpenAPI, AsyncAPI, Protobuf) and detect breaking changes. Use when an API spec changes.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8, §4.6"
  stage: TEST
  inputs: [contract]
  outputs: [test-suite]
  repo_roles: [app, contracts]
---

# Schema Validation


## Purpose
Two deterministic checks: (1) the implementation conforms to its declared schema; (2) a schema change
is backward/forward compatible as its compatibility policy requires.

## When this applies
- Files changed include `openapi*.yaml|json`, `*.schema.json`, `asyncapi*.yaml`, `*.proto`, `*.avsc`,
  or serializer/DTO code. These are always-overlap path classes for snapshot staleness (plan §4.5).

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, contracts]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Schema source.** The OpenAPI, JSON Schema, Avro or Protobuf definition resolves as `repo@sha:path` from the contracts repo. Never validate against a schema inferred from code.

Never proceed on a missing input silently.

## Procedure
1. **Lint the spec**: `spectral lint openapi.yaml` (OpenAPI/AsyncAPI), `buf lint` (Protobuf).
2. **Breaking-change detection** against the base branch *and* against the version recorded as deployed:
   | Format | Tool |
   |---|---|
   | OpenAPI | `oasdiff breaking base.yaml head.yaml --fail-on ERR` |
   | Protobuf | `buf breaking --against '.git#branch=main'` |
   | Avro / JSON Schema / Protobuf on Kafka | Schema Registry compatibility check (`BACKWARD`, `FORWARD`, `FULL`, `*_TRANSITIVE`) |
   | JSON Schema | `json-schema-diff` or a registry compatibility check |
3. **Conformance**: validate real responses against the spec in integration tests — Schemathesis
   (property-based, generates requests from OpenAPI), or response validation middleware in the test env:
   `schemathesis run openapi.yaml --base-url http://localhost:8080 --checks all`.
4. **Compatibility direction**: for events, check both old producer → new consumer and new producer → old consumer.
   Removing a field, tightening a type, adding a required field, or renaming an enum value is breaking unless
   proven otherwise.
5. A breaking change that is intended needs a versioning decision (`DECISION` entry; architect `REVIEWED`)
   and, at HIGH/CRITICAL, human approval per the approval matrix.

## Outputs
- Lint/diff/conformance tool output → `VERIFIED` via CI. Judgment that a break is acceptable → `REVIEWED` + `DECISION`.
- Tool unavailable or inconclusive → treat as `INCOMPATIBLE` (plan §5.3) and record `COMPATIBILITY_UNKNOWN`.

## Enforcement
**Enforced** — see rules below.

The diff tools are deterministic CI gates. Fail-safe default is enforced by compatibility-check.

## References
- [`../pact-consumer-driven/SKILL.md`](../pact-consumer-driven/SKILL.md)
- [`../../../contracts/`](../../../contracts/)
- [`../../../change-management/snapshot/reference/staleness-policy.md`](../../../change-management/snapshot/reference/staleness-policy.md)
