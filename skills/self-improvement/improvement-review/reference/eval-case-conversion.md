# Lesson → Synthetic Reproduction

Don't build a custom eval harness. skill-creator's loop (draft → test prompts → grade → analyze
→ iterate, backed by `evals.json` / `grading.json`) is the harness (§2 Phase 0).

[ADR 0006](../../../../docs/adr/0006-self-improvement-lessons.md) §3: every lesson gets a
**synthetic** minimal scenario that triggers its failure class. It is built **from the lesson**,
never copied or paraphrased from the real case (which stays behind ledger pointers in the
project).

## Red / green rule
| Run | Required result | Recorded as |
|---|---|---|
| Reproduction on the **current** skill | **Fails** (the failure class shows up) | `repro.fails_on_current: true` |
| Reproduction on the **revised** skill (or with the new gate/lint active) | **Passes** | `repro.passes_on_revision: true` |
| Skill's existing evals on the revision | No regressions | grading evidence on the REVIEWED candidate |

A reproduction that already passes on the current skill does not capture the failure. Rewrite
it, or dismiss the cluster. After approval it becomes a **permanent regression eval** for that
skill.

## Form (skill-creator `evals.json`)

```json
{
  "skill_name": "story-writer",
  "evals": [
    {
      "id": 3,
      "lesson_id": "LES-14",
      "prompt": "Write stories for: 'Users can update their shipping address. Postcode must be 5 digits; street is required.'",
      "expected_output": "Stories whose AC include at least one negative criterion per validated field.",
      "files": [],
      "expectations": [
        "At least one AC covers a postcode that is not 5 digits",
        "At least one AC covers a missing street",
        "Every AC has an ID of the form ST-<n>/AC-<n>"
      ]
    }
  ]
}
```

## Rules
1. **Synthetic only.** Use generic domains (shipping address, to-do list, library loans) that
   share the lesson's *shape*, not the project's subject. Reserved values only: `example.com`,
   RFC 5737 IPs, PSP test cards, `555-01xx` numbers.
2. **Minimal.** The smallest prompt and files that trigger the class. No fixtures beyond what
   the failure needs.
3. **Checkable expectations.** Each expectation can be graded `passed` with `evidence` from the
   output alone (`grading.json`). For a GATE/LINT remedy, the expectation is that the check
   reports the finding (`check_id`) on the red output.
4. **Sanitized.** The `evals.json` file passes `scripts/sanitize_check.py` (blocklist, PII and
   secrets, 8-word verbatim overlap with project files) before it leaves the project.
5. **Versioned.** Each eval records the `lesson_id` and the `platform_release_sha` it was
   created against.
6. **Keep positives.** Strongly verified positive patterns become regression evals too, so a
   revision cannot fix one pattern by breaking working behavior.
