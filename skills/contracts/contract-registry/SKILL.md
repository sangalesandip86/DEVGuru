---
name: contract-registry
description: Registers and looks up the contracts between services — HTTP/gRPC/GraphQL APIs and events — with their type, provider, consumers, and compatibility policy. Use when a change touches an API or event schema, when an API_CONTRACT story is written, or when dependency discovery surfaces a cross-repo call.
metadata:
  group: contracts
  phase: 3
  binding: true
  plan-ref: "§4.6, §6"
  stage: ARCHITECTURE
  inputs: [architecture-package]
  outputs: [contract]
  repo_roles: [contracts, app]
---

# Contract Registry

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Make inter-service contracts explicit so compatibility can be checked against what is actually
deployed. Built in Phase 3 from the dependency patterns Phase 2 discovery actually surfaced — not a
speculative model.

## When this applies
- A change touches an API spec, a route, a client, or an event schema.
- `dependency-discovery` reports a cross-repo edge with no registered contract.
- An `API_CONTRACT` story is created (v3.1 §4.12 requires a registry entry).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Primary stage ARCHITECTURE (integration/contract inventory); also used at DESIGN when a story changes a contract.

- **Inputs:** the integration inventory from the architecture package, or the story's `touches.api_contracts`.
- **ADOPT:** existing OpenAPI/AsyncAPI/protobuf/JSON Schema files found in resolved repos are registered as DRAFT contracts citing `repo@sha:path`.
- **ASK/create:** if no `contracts` repo exists and the architecture calls for shared contracts, propose local creation or a `repo-request.yaml` via repo-bootstrap.
- **Repo roles:** `contracts` (registry source), `app` (provider/consumer code).

## Procedure
1. Look up existing contracts for the provider and consumers involved (registry export, or the
   contract_registry module of the adlc MCP server — plan's Server 3).
2. If none exists, propose one per [contract-schema.md](reference/contract-schema.md):
   `mcp:adlc.register_contract` with id, provider, consumers, spec reference (`repo@sha:path` +
   content hash), type, and compatibility policy.
3. Record the Change Set's `contracts[]` with the version it changes or depends on.
4. Hand the contract to `../compatibility-check/SKILL.md` before integration.
5. A cross-repo edge with no contract and no way to establish one stays an `UNRESOLVED` dependency.

## Outputs
- Contract registration (PROPOSAL until the change that introduces it is merged).
- `FACT` entries for the spec location and hash; `DECISION` for the chosen compatibility policy.

## Enforcement
Registration is a server tool call; `record_deployment` is fed by CI only (no agent caller).
Whether every cross-repo edge has a contract is guideline only until `drift-detection` runs in CI.

## References
- [reference/contract-schema.md](reference/contract-schema.md)
- [../compatibility-check/SKILL.md](../compatibility-check/SKILL.md)
- [../drift-detection/SKILL.md](../drift-detection/SKILL.md)
- [../../change-management/dependency-discovery/SKILL.md](../../change-management/dependency-discovery/SKILL.md)
