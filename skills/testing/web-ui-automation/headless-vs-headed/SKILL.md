---
name: headless-vs-headed
description: Decides when browser tests run headless vs headed (and on which browser channels), and diagnoses failures that appear in only one mode. Use when configuring CI browser execution or when a test passes headed locally but fails headless in CI.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [test-suite]
  outputs: [test-suite]
  repo_roles: [app, tests]
---

# Headless vs Headed Execution

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Run the cheapest mode that still represents real users, and explain mode-specific failures with
evidence instead of retries.

## When this applies
- Configuring browser execution for CI or a new test project.
- A test's outcome depends on the mode it runs in.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Failure evidence.** You need the failing run's trace, screenshot or JUnit from CI, and a local headed run on the same commit. Without evidence from both modes, the diagnosis is an INFERENCE.

Never proceed on a missing input silently.

## Procedure
1. Apply the defaults:

   | Context | Mode | Notes |
   |---|---|---|
   | CI gating suite | Headless (Chromium, Firefox, WebKit) | Fast and parallel; Chrome's new headless is the real browser, not a separate engine |
   | Local authoring/debugging | Headed, `--debug` or UI mode | Prefer traces to watching runs |
   | Branded channels (`chrome`, `msedge`) | Headless, nightly | For codecs, DRM, enterprise policies |
   | Extensions, hardware WebAuthn, some permission/media prompts | Headed under Xvfb (`xvfb-run`) | Document why headless is insufficient |
   | Visual baselines | Same mode and container as CI, always | Mode changes rendering |

2. When a test passes headed but fails headless, check in order:
   1. Viewport and device scale factor — headless defaults differ from a desktop window; set `viewport` explicitly.
   2. User-agent sniffing — `HeadlessChrome` in the UA may trigger app or bot-protection branches.
   3. Fonts/GPU — missing fonts in the CI image shift layout; WebGL may fall back to software rendering.
   4. Timing — headless is faster and exposes races (flaky-test-patterns #1–#4).
   5. Permissions, clipboard, downloads — grant them explicitly via context options.
3. Record the root cause as an `INFERENCE` citing traces from both modes.

## Outputs
- Config recommendations → `PROPOSAL`; diagnoses → `REVIEWED`; run results → `VERIFIED` from CI.

## Enforcement
Guideline only — no enforcement point yet.

## References
- [`../playwright-expert/reference/flaky-test-patterns.md`](../playwright-expert/reference/flaky-test-patterns.md)
- [`../visual-regression/SKILL.md`](../visual-regression/SKILL.md)
