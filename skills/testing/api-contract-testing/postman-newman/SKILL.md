---
name: postman-newman
description: Builds and runs Postman collections headlessly with Newman in CI, with environment files, scripted assertions, and JUnit output. Use when a team maintains API tests as Postman collections or needs black-box API smoke tests against a deployed environment.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [contract, test-design]
  outputs: [test-suite]
  repo_roles: [app, tests, contracts]
---

# Postman / Newman

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Turn Postman collections into reproducible CI checks, mainly API smoke and black-box regression tests
against deployed environments.

## When this applies
- Repo contains `*.postman_collection.json`, or the team's API tests live in Postman.
- Post-deploy smoke tests are needed (see [`../../security-testing/deployment-verification/SKILL.md`](../../security-testing/deployment-verification/SKILL.md)).

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests, contracts]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Collection and environment.** The collection lives in the repo. Environment variables are names only (`required-secrets.yaml`), and CI injects the values.

Never proceed on a missing input silently.

## Procedure
1. **Collections in git**, exported (Collection v2.1) and reviewed like code; no tests that exist only in a Postman workspace.
2. **Assertions in test scripts**, not by eye:
   ```js
   pm.test('status is 201', () => pm.response.to.have.status(201));
   pm.test('matches schema', () => pm.response.to.have.jsonSchema(pm.collectionVariables.get('orderSchema')));
   pm.collectionVariables.set('orderId', pm.response.json().id);
   ```
3. **Environments**: one file per environment with **no secrets** in it. Inject secrets at runtime
   (`--env-var "token=$API_TOKEN"`) from the CI secret store. A secret found in a collection or environment
   file is a secret-scanning finding.
4. **Run**:
   ```bash
   newman run api.postman_collection.json -e staging.postman_environment.json \
     --env-var "token=$API_TOKEN" --bail --reporters cli,junit \
     --reporter-junit-export results/newman.xml
   ```
5. **Order dependence**: chained requests are fine for a scenario, but each folder must set up its own
   data so folders can run independently (`--folder`).
6. Newman is not a contract-testing tool: where consumers exist, add Pact or schema validation.

## Outputs
- Collections (`REPO_WRITE`). JUnit results from CI → `VERIFIED`. Coverage gaps → `REVIEWED`.

## Enforcement
Pass/fail is machine evidence from CI. Secret hygiene is enforced by secret scanning, not this skill.

## References
- [`../schema-validation/SKILL.md`](../schema-validation/SKILL.md)
- [`../../security-testing/secret-scanning/SKILL.md`](../../security-testing/secret-scanning/SKILL.md)
