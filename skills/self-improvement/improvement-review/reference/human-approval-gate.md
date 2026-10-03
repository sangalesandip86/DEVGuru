# Human Approval Gate

Self-improvement follows the identical authority split as every other change in the platform
(§5.5). It does not get a quieter path to production.

| Step | Authority | Set by | Basis |
|---|---|---|---|
| Lesson + reproduction drafted | `DRAFT` | Reviewer agent (never the failing role) | Cluster above threshold; `lesson_lint.py` PASS; reproduction red on the current skill |
| Revision drafted | `PROPOSED` | improvement-review | Diff (or gate/lint change) per remedy selection |
| Reproduction green, no regressions in the existing evals | `REVIEWED` | Server, recording skill-creator grading evidence | Automated evidence of improvement — **not** approval |
| Sanitization | `sanitization.result: PASS` | `sanitize_check.py` | Fail-closed; content that fails stays project-local |
| Human approves **lesson and reproduction together** | `APPROVED` | Authenticated human (CODEOWNERS on `skills/**`) | PR review event ingested by the server |
| Live skill / gate replaced; repro becomes a permanent regression eval | — | Merge of the approved PR; `platform_release_sha` advances | Forge merge event |
| Lesson shared at `ORG` scope | `scope: ORG` | `record_lesson`, only after APPROVED | ADR 0006 §6 |

## What the approver sees
The request is formatted with `grounding/human-review-format` and contains:
- the lesson (skill, step, class, `occurrences`, `what_failed`, `advice`, `check`)
- the synthetic reproduction and its red/green results (`grading.json` per expectation)
- regression results on the skill's existing evals
- the remedy kind and the full diff, including what it replaces or merges into, and the
  skill's body line count against the 500-line budget
- the sanitization result (blocklist, PII/secret, verbatim-overlap findings: none)
- any pruning proposals for remedies unfired for 6 months

The approver does **not** see the real case unless they open the ledger pointers inside the
project, under its access controls.

## Rules
1. A `REVIEWED` candidate is never deployed. Only `APPROVED` replaces the live skill or gate.
2. The lesson and its reproduction are approved **together**. Approving advice without a
   red/green reproduction is not possible (`lesson.schema.json` requires both flags true for
   `APPROVED`).
3. A skill, prompt, policy, gate, or lint change is a **control-file** write: always `CRITICAL`
   tier, regardless of how small the diff is.
4. `ORG` scope requires `APPROVED` and a sanitization PASS. There is no path to share an
   unapproved or unsanitized lesson.
5. A rejected candidate is recorded `REJECTED` with a reason. Its incidents return to OPEN or
   are DISMISSED by the human.
6. Rolling back a revision, or pruning a remedy, is an ordinary PR — also human-approved.
