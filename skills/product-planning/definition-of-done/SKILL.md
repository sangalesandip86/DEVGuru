---
name: definition-of-done
description: Check the Definition of Done -- evidence a story needs for DONE and ACCEPTED. Use when verifying a story or interpreting NOT_DONE.
metadata:
  group: product-planning
  phase: 1
  binding: true
  plan-ref: "§4.12, §5.4, §5.5, §5.10"
  stage: REVIEW
  inputs: [ready-story, change-set]
  outputs: [review-verdict]
  repo_roles: [planning, app]
---

# Definition of Done

## Purpose
DONE means the story's acceptance criteria are demonstrably met in integrated code, with every
gate its risk tier requires backed by machine evidence and the required reviews recorded.
ACCEPTED means a human product owner agrees it delivers the value, where the policy requires that.

Like the DoR, this skill explains the rule, and `completion_gate.py` (SYSTEM CI) decides it.

## When this applies
- During implementation, so you know what evidence must exist at the end and can design tests and tags for it.
- After the linked Change Sets merge, or whenever new evidence lands.
- When the completion gate reports NOT_DONE.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Stage REVIEW (evaluated through INTEGRATE).

- **Inputs:** the story, its linked Change Sets, test results and ac-coverage output.
- **BACKFILL:** missing test evidence → propose running the TEST stage; DONE is never assumed.
- **Repo roles:** `planning`, `app`.

## What DONE requires
Full table: [reference/completion-gate.md](reference/completion-gate.md). The **standard** variant needs:
- the story passed the readiness gate **at its current AC hash** (AC freeze);
- at least one linked Change Set, with every linked one INTEGRATED (an observed merge, never self-reported);
- every `automated` criterion covered by ≥1 **passing** test, via [`ac_coverage.py`](../../enforcement/ci-checks/planning-gates/ac_coverage.py) and test tags `ST-n/AC-n`;
- every `manual` criterion carrying a verification record from qa-diagnose or a human, at the current AC hash;
- every machine gate for the effective tier VERIFIED (`tier_gates`: LOW `ci`; MEDIUM `+unit-tests`; HIGH `+sast, sca`; CRITICAL `+staged-rollout`), plus `secret-scan`;
- the diff within `affected_paths` and no riskier than the planned tier;
- code-reviewer ACCEPT;
- conditionally: contract compatibility, migration rollback test, accessibility, security-reviewer ACCEPT, observability and docs reviews;
- no OPEN blocking QUESTION and no unexpired ASSUMPTION above LOW.

The **spike** variant instead needs a DECISION with a merged ADR, follow-up stories
(`follow_up_of`), and **no production code merged**.

**ACCEPTED** adds `human:product-owner` acceptance for FEATURE/UI stories at MEDIUM and above,
and for every non-spike story at HIGH and above. Otherwise DONE is terminal.

## Procedure (for the implementing roles)
1. **Developer:** reference the story in the PR body (`Implements: ST-n`). Name the AC each task addresses (`ac_refs`). Stay inside `affected_paths`. If you must go outside them, stop and re-plan, because a riskier diff fails `within_scope`.
2. **qa-derive/qa-diagnose:** tag every test with the AC id it verifies. Record the manual-criterion verifications with the `ac` field.
3. **Before asking for review:** dry-run `completion_gate.py` with a local coverage report, then fix MISSING items. Never "explain away" a gate in the PR description.
4. **Never claim DONE** in prose or in a handoff. Report the gate result, citing the CI run.

## Enforcement
**Enforced** — see rules below.

- **DONE and ACCEPTED are computed only by** `completion_gate.py` + `ac_coverage.py` (SYSTEM). There is no agent tool for story status (plan §5.6 row "Story is DONE only when the DoD is met").
- **VERIFIED gates come only from SYSTEM evidence:** gate records with any other `actor_type` are ignored.
- **INTEGRATED comes only from observed forge events** (plan §5.10).
- **The policy** is a control file and cannot be weakened by agents.

## References
- [reference/completion-gate.md](reference/completion-gate.md)
- [../policies/dod-policy.yaml](../policies/dod-policy.yaml)
- [story-writer/reference/acceptance-criteria-standard.md](../story-writer/reference/acceptance-criteria-standard.md) (test tagging)
- [change-management/change-set/reference/completion-criteria.md](../../change-management/change-set/reference/completion-criteria.md): a Change Set's own INTEGRATED criteria, which the DoD builds on
