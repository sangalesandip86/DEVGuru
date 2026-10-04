
# Pattern Threshold

A single incident is an anecdote. A lesson is drafted only when a pattern is established.

## Cluster key
Incidents cluster by **`(skill, step, failure_class)`** ([ADR 0006](../../../../docs/adr/0006-self-improvement-lessons.md)).
Because the class comes deterministically from the catching check, two incidents for the same
step and class are the same pattern even though no task text is compared.

## Thresholds
All values are **default policy values**, tunable from ledger data.

| Signal type | Threshold to draft a lesson | Window |
|---|---|---|
| Negative (deterministic `check_id`) | ≥ 3 incidents across ≥ 2 distinct Change Sets | 30 days |
| Negative (judgment-only, `check_id: null`) | ≥ 3 incidents with notes from ≥ 2 distinct catchers (reviewer or human) | 30 days |
| Routing near-miss (`skill-router:mandatory_near_miss`) | ≥ 2 | 30 days |
| Production | 1 incident with severity HIGH/CRITICAL; otherwise ≥ 2 | 90 days |
| Efficiency (same skill step over budget) | ≥ 5 incidents, or median overrun > 50% | 30 days |
| Human override / risk downgrade rate | > 20% of escalations for one reason code | 30 days |
| Positive (strongly verified only) | Never drafts a lesson. ≥ 3 positives for a step become regression evals that any revision of that step must keep passing | — |

Distinct Change Set counts are computed inside the project ledger from `evidence_refs`; the
lesson carries only the counts (`occurrences`).

## Exclusions
- `unverified-positive` incidents never count.
- Incidents from an older `platform_release_sha` count only if the implicated step's text is
  unchanged since then.
- Incidents whose evidence is only EXTERNAL_UNSTRUCTURED are reviewed by a human before they
  count (they may be adversarial).

## Rising override rate
A rising human-override or risk-downgrade rate is an adoption-health signal (§7), not noise to
average away. Always surface it in the review summary, even below threshold.
