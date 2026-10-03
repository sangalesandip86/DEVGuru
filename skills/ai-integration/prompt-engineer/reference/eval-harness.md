# Eval Harness

<!-- reconstructed: v2 source not provided; review -->

## Rule: do not build a custom eval harness

Per plan §2 (Phase 0): **skill-creator's existing loop is the harness** —
draft → test prompts → grade → analyze → iterate, backed by `evals.json` and `grading.json`.
Every prompt and skill change in this platform, including self-improvement candidates, is
evaluated through that loop. Write cases in its format; do not invent a parallel format,
runner, or results store.

If a product feature (not a platform skill) needs evals in CI, export the same case format
and grade with the same rubric shape, so cases move between the two without conversion.

## Case design

Each case in `evals.json` should specify:

| Field | Content |
|---|---|
| id | Stable identifier (`<skill>-<n>`) |
| prompt / input | The exact input, including any files or context |
| expectations | Checkable properties of a good output — prefer objective ones |
| source | Why this case exists: incident id, ledger `entry_id`, or requirement |

Good expectations are verifiable: "output cites `file:line` for each RISK", "returns
`null` when the answer isn't in the documents", "does not modify files under `.claude/`".
Avoid "output is high quality".

## Coverage mix

| Bucket | Share | Purpose |
|---|---|---|
| Typical cases | ~50% | Core behavior |
| Edge cases | ~25% | Empty input, long input, ambiguous input, missing numbers |
| Regression cases | ~15% | Every past failure becomes a case (`../../../self-improvement/improvement-review/reference/eval-case-conversion.md`) |
| Adversarial cases | ~10% | Injected instructions in data, attempts to set APPROVED, control-file writes (see `../../../testing/ai-agent-testing/`) |

Hold out ≥20% of cases from the editing loop to detect overfitting.

## Grading

1. **Deterministic checks first** — schema validity, regex/citation presence, file-path
   assertions, exact-match where applicable. These results are machine evidence.
2. **Model-graded rubric** for qualitative expectations — use a grader from a different model
   family than the one under test for HIGH/CRITICAL skills (`../../../roles/reference/reviewer-diversity.md`).
3. **Human spot-check** a sample of model-graded results each iteration to calibrate the grader.

Run each case ≥3 times; report pass rate, not a single pass/fail.

## Authority mapping

| Result | Status |
|---|---|
| Candidate beats baseline, no held-out regressions | `REVIEWED` |
| Deterministic CI eval job passed, ingested by the server | `VERIFIED` (set by server, never by the agent) |
| Human accepts the candidate for production | `APPROVED` |
