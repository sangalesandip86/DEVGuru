# Pilot & Measurement

Plan v3.1 §7. Nothing in the platform means anything without a way to tell whether it helps. Fill
in sections 1 and 6 **before the first Change Set runs**.

## 1. Baseline — five numbers per pilot repo

Measure over the 60 days before the platform touches the repo; re-measure on the same
definitions every 2 weeks during the pilot.

| Metric | Definition | Source | Baseline | Current |
|---|---|---|---|---|
| Lead time | first commit on branch → merged to default branch (median, hours) | forge API | | |
| Change-failure rate | % of merged changes later linked to an incident, rollback, or hotfix | incident tracker + forge | | |
| Rework rate | % of merged lines modified again within 21 days | git history | | |
| Review time per PR | PR ready-for-review → first approving review (median, hours) | forge API | | |
| Cost per merged change | (model spend + reviewer hours × rate) / merged PRs | ledger cost fields + billing | | |

Repo: `______`  Baseline window: `____-__-__` → `____-__-__`  Measured by: `human:______`

## 2. Human-override rate

A rising override rate is an adoption-health signal, not noise to average away.

| Signal | Ledger query | Weekly count | Rate |
|---|---|---|---|
| Risk-tier downgrades by a human | `DECISION` entries with reason `TIER_DOWNGRADE` (§4.5) | | / tier computations |
| Human overrides of an agent recommendation | `DECISION` by `actor_type=HUMAN` with `parent_entry_id` pointing to an agent `PROPOSAL` it rejects | | / agent proposals |
| Phase-2 routing near-misses | self-improvement incidents `type=ROUTING_NEAR_MISS` | | / Change Sets |

Alert threshold (default): override rate up >50% week-over-week, or above 25% absolute.

## 3. Planning health (v3.1, §4.12)

| Metric | Definition | Source | Weekly value |
|---|---|---|---|
| DoR escape rate | % of READY stories that later raise a blocking `QUESTION` or return to REFINING | ledger status entries from `readiness-gate` + QUESTION entries | |
| Split rate after READY | % of READY stories later split into new stories | plan-file history (`plans/stories/`) | |
| Size calibration | predicted size vs actual diff (ratio, median and p90) | story size field vs merged diff | |
| AC coverage ratio at DONE | AC with at least one executed, passing test / total AC | `ac-coverage` CI job | |

Reading them: a high escape rate means the DoR is too weak; falling throughput with a
near-zero escape rate means the DoR is too heavy.

## 4. Test health (v3.1, §4.13)

| Metric | Definition | Source | Weekly value |
|---|---|---|---|
| Integrity-guard findings per PR | `test-integrity-guard` findings (weakened assertions, mass snapshot updates, no-assertion tests, mocked SUT, swallowed failures) / PRs touching tests | CI job output → ledger FACTs | |
| Escaped-defect rate, agent-written tests | production defects in code covered by agent-written tests / Change Sets with agent-written tests | ledger `CHALLENGED` entries joined to test-engineer handoffs | |
| Mutation score trend | diff-scoped mutation score, median per PR, week over week | mutation CI job | |
| New-test flake rate | new/changed tests failing ≥1 of 5 random-order runs / new tests | new-test flake gate | |

A falling mutation score with rising coverage means tests are being written to run code, not to
check it.

## 5. Guard rails in force during the pilot

- **Change-size cap** — above `max_diff_lines` (default 400 changed lines, excluding
  generated/lockfiles), risk-tiering requires decomposition before implementation.
- **Autonomy gated by verification strength** — every pilot repo starts in `ASSIST` unless
  it meets the thresholds in
  `skills/governance/autonomy-gating/reference/verification-strength.md`.

## 6. Exit criteria (write before starting)

| Outcome | Criteria (all over the final 4 weeks vs baseline) |
|---|---|
| **Succeeded** | lead time ≤ ___% of baseline; change-failure rate not higher than baseline; rework rate ≤ baseline + ___ pts; cost per merged change ≤ ___ |
| **Failed** | change-failure rate > baseline + ___ pts; or override rate > ___%; or rework rate > baseline + ___ pts |
| **Inconclusive** | neither — extend ___ weeks once, then decide |

Signed off before start by: `human:tech-lead ______` `human:product-owner ______`  Date: `____-__-__`
