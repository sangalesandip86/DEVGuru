---
name: device-matrix
description: Selects the minimal set of devices, OS versions, and form factors to test on, driven by real usage analytics and the change's risk tier. Use when planning mobile test coverage or choosing device-farm runs (Firebase Test Lab, BrowserStack, AWS Device Farm).
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [change-set]
  outputs: [test-suite]
  repo_roles: [app, tests]
---

# Device Matrix

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Cover the devices users actually have, at a cost proportional to risk. Testing on "every device"
is neither affordable nor necessary.

## When this applies
- Planning mobile verification for a Change Set, or reviewing a device-farm budget.
- A defect is reported on a specific device/OS.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Usage data.** Real device and OS analytics for the app. Without them, the matrix is an ASSUMPTION (top OS versions by market share), recorded with an expiry.

Never proceed on a missing input silently.

## Procedure
1. **Source the population**: pull device/OS share from production analytics (Firebase, App Store
   Connect, Play Console). Cite the export and its date. Without analytics, use public market share
   and record an `ASSUMPTION` with an expiry.
2. **Build tiers**:

   | Tier | Contents | When it runs |
   |---|---|---|
   | Core | Lowest supported OS, latest OS, most-used device per platform, one small screen, one tablet/foldable if supported | Every PR (emulator/simulator) |
   | Extended | Devices covering ≥ 90% cumulative usage; OEM skins (Samsung One UI, Xiaomi HyperOS) | Nightly on a device farm |
   | Targeted | Devices from crash reports or the defect being fixed | When the Change Set touches that area |

3. **Tier rules**: risk tier HIGH/CRITICAL on mobile → Extended must run before release. Changes to
   camera, Bluetooth, biometrics, push, background work, or payment SDKs always add real devices —
   emulators don't exercise those faithfully.
4. **Dimensions to vary deliberately**: OS version, screen size/density, locale (RTL), font scale and
   accessibility settings, low-memory devices, network conditions.
5. Re-derive the matrix quarterly or when the minimum supported OS changes.

## Outputs
- Matrix → `PROPOSAL` (`REVIEWED` once checked). Device-farm results → `VERIFIED` via CI ingestion.
- Unsupported-but-used devices → `RISK`.

## Enforcement
Guideline only — no enforcement point yet.

## References
- [`../appium-expert/SKILL.md`](../appium-expert/SKILL.md)
- [`../../test-architecture/test-strategy/SKILL.md`](../../test-architecture/test-strategy/SKILL.md)
