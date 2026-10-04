---
name: prompt-engineer
description: Design and evaluate prompts and system instructions for LLM features and skills. Use when writing, changing, or debugging a prompt.
metadata:
  group: ai-integration
  phase: progressive
  binding: false
  plan-ref: "§4.10"
  stage: DESIGN
  inputs: [ready-story]
  outputs: [test-design]
  repo_roles: [app]
---

# Prompt Engineer


## Purpose

Treat prompts as code: every change is driven by failing eval cases and justified by
measured improvement, not by how the new wording reads. Output is `REVIEWED` (an eval run
plus judgment); a prompt change reaches production only via human `APPROVED`.

## When this applies

- A product feature's prompt is created or changed.
- A platform skill/role prompt is revised — including candidates from
  `../../self-improvement/improvement-review/SKILL.md`.
- Quality regression reported against an LLM feature.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Primary stage DESIGN; prompts are designed against a READY story's AC and evaluated with the skill-creator eval loop.

- **Inputs:** a READY story and any existing prompts/evals.
- **ADOPT:** existing prompts and eval files in the repo are imported and baselined before changes.
- **BACKFILL:** no READY story → propose `BACKFILL: PLAN`.
- **Repo roles:** `app`.

## Existing project standards
On an existing repo, load [project-conventions](../../engineering-design/project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Follow the project's existing prompt storage, templating and eval layout.

## Procedure

1. **Define success before writing.** Write or extend eval cases first
   ([`reference/eval-harness.md`](reference/eval-harness.md)): inputs, expected properties,
   grading method. Include the failing cases that motivated the change.
2. **Baseline.** Run the current prompt against the eval set; record pass rate per case as the baseline.
3. **Draft the change** using [`reference/prompt-patterns.md`](reference/prompt-patterns.md).
   Change one thing per iteration when diagnosing.
4. **Run and compare.** Same eval set, same model(s), ≥3 runs per case for non-deterministic
   outputs. Report pass rate delta per case — improvements *and* regressions.
5. **Check for overfitting.** Hold out ≥20% of cases not looked at while editing; a gain only
   on seen cases is not a gain.
6. **Record.** `PROPOSAL` with the diff, baseline vs. candidate results, and model id(s).
   Mark the prompt revision `REVIEWED` only when it beats baseline without regressions on held-out cases.
7. **Hand off for human approval.** Platform skill/prompt edits are control files: CRITICAL
   tier, human `APPROVED` required (`../../grounding/trust-boundaries/reference/control-files.md`).

## Outputs

- `PROPOSAL` (prompt diff) with linked eval results (`evals.json` / `grading.json` artifacts).
- `DECISION` `REVIEWED` ACCEPT/REJECT on the candidate.
- `QUESTION` when success criteria for the feature are not stated.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.


- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Writes to skills/agent definitions are denied to agents by managed settings + `PreToolUse`
  control-file guard (§5.6 row 3) — this skill proposes; it cannot install.
- Eval-first discipline: **guideline only — no enforcement point yet**.

## References

- [`reference/prompt-patterns.md`](reference/prompt-patterns.md)
- [`reference/eval-harness.md`](reference/eval-harness.md)
- `../llm-integration-architect/SKILL.md`
- `../../self-improvement/improvement-review/reference/eval-case-conversion.md`
