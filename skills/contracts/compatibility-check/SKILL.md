---
name: compatibility-check
description: Checks whether an application version can be deployed to an environment by verifying its contracts in both directions against the versions actually recorded as deployed there. Use before integrating or releasing any change that touches a registered contract, and for every API_CONTRACT story.
metadata:
  group: contracts
  phase: 3
  binding: true
  plan-ref: "§4.6, §6"
  stage: REVIEW
  inputs: [contract, change-set]
  outputs: [review-verdict]
  repo_roles: [contracts, app]
---

# Compatibility Check

## Purpose
Answer "can I deploy?" against **recorded deployed versions** (from `record_deployment`, fed by
CI) — not "latest against latest", and not a guess.

## When this applies
- Any change to a registered contract's provider or consumer.
- Before `INTEGRATED` for HIGH-tier contract changes; before `RELEASED` for every environment.
- `API_CONTRACT` stories: compatibility-check `VERIFIED` is a DoD item (v3.1 §4.12).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Runs at REVIEW for any Change Set that changes a contract; also callable at DESIGN as a dry run.

- **Inputs:** old and new contract versions plus recorded deployments.
- **BACKFILL:** none — missing deployment or verification data yields INCOMPATIBLE (`COMPATIBILITY_UNKNOWN`), never a pass.
- **Repo roles:** `contracts`, `app`.

## Procedure
1. Export the registry (contracts, verifications, deployments) from the contract_registry module of
   the adlc MCP server (plan's Server 3), or use `mcp:adlc.check_compatibility` directly.
2. Run:
   ```bash
   python skills/contracts/compatibility-check/scripts/check-can-i-deploy.py \
     --registry registry.json --application billing --version 1.4.0 --environment prod
   ```
   Exit 0 = deployable, 1 = not deployable, 2 = input error.
3. Directions checked: new producer → each deployed consumer; deployed producer → new consumer;
   for event contracts, also every retained producer version → new consumer.
4. Any missing verification or deployment record → `INCOMPATIBLE` by default with reason code
   `COMPATIBILITY_UNKNOWN` → escalate the tier one level (`change-management/risk-tiering`).
5. Never mark a result COMPATIBLE from reading the specs yourself. An agent's reading of two specs is
   at most a `REVIEWED` judgment; `VERIFIED` comes only from the script/server run on CI evidence.

## Outputs
- `FACT` entry: the script output (written by hook/CI).
- `VERIFIED` gate status — set by the server from the CI run, never by an agent.
- `RISK` entry for every INCOMPATIBLE or UNKNOWN check.

## Enforcement
Run as a required CI check before merge/deploy; the server sets `VERIFIED` from the result (§5.5).
Agents have no tool that writes deployment records or verification results.

## References
- [scripts/check-can-i-deploy.py](scripts/check-can-i-deploy.py) — tests: `python -m unittest discover -s skills/contracts/compatibility-check/tests`
- [../contract-registry/reference/contract-schema.md](../contract-registry/reference/contract-schema.md)
- [../drift-detection/SKILL.md](../drift-detection/SKILL.md)
- [../../testing/api-contract-testing/pact-consumer-driven/SKILL.md](../../testing/api-contract-testing/pact-consumer-driven/SKILL.md)
