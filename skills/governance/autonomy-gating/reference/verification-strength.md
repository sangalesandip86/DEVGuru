# Verification Strength

A repository's autonomy is gated by its own verification strength, not just a change's risk
tier (plan §4.11, §7).

## Inputs (all machine-sourced)

| Metric | Source | Window |
|---|---|---|
| CI pass reliability — % of runs on unchanged code that pass (flake-adjusted) | CI history | last 30 days |
| Changed-code coverage — % of lines changed in merged PRs covered by tests | coverage tool diff report | last 20 merged PRs |
| Acceptance-criteria exercise rate — % of acceptance criteria linked to at least one executed test | qa-derive handoffs + CI | last 20 Change Sets |
| Escaped-defect rate — production incidents linked to Change Sets | ledger `CHALLENGED` entries | last 90 days |
| Diff-scoped mutation score — % of mutants in changed code killed by the suite (v3.1 §4.13; VERIFIED evidence) | mutation job in CI | last 20 merged PRs |
| Red/green proof rate — % of BUG_FIX / new-AC changes whose new tests fail on base SHA and pass on head SHA (v3.1 §4.13; VERIFIED evidence) | `red-green-check` CI job | last 20 qualifying PRs |

## Levels (default policy values — tune from pilot data)

| Level | Criteria (all must hold) | Effect |
|---|---|---|
| `ASSIST` | default; or any criterion below `SUPERVISED` | Human reviews every change before merge, regardless of tier |
| `SUPERVISED` | CI reliability ≥ 95%, changed-code coverage ≥ 60%, AC exercise ≥ 70%, mutation score ≥ 50%, red/green proof ≥ 80% | Approval matrix applies as written; LOW still gets a human glance |
| `AUTONOMOUS_LOW` | CI reliability ≥ 98%, changed-code coverage ≥ 80%, AC exercise ≥ 90%, mutation score ≥ 70%, red/green proof ≥ 95%, no escaped defects in window | LOW-tier changes may merge on `VERIFIED` without a human |

No level ever relaxes MEDIUM+ requirements in the approval matrix, and no level touches
control files (always CRITICAL, always human).

## Rules
- Coverage without mutation score is not enough: coverage shows code ran, the mutation score shows the tests would notice it breaking.
- Missing data → `ASSIST`. Never infer strength from absence of failures.
- A level downgrades immediately on threshold breach; upgrades require two consecutive
  windows above threshold.
- Every level change is a `DECISION` ledger entry with the metric values as sources.
- The same strength signal decides whether a clean run counts as a positive signal or is
  tagged `unverified-positive` in self-improvement.
