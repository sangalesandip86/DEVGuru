# Quantitative Risk Model

## Formula

```
score = sigmoid(bias + Σ(weight_i × feature_i))
sigmoid(x) = 1 / (1 + e^(-x))
```

## Model Parameters (v1.0.0)

| Parameter | Value | Rationale |
|---|---|---|
| bias | -3.2 | Shifts baseline toward LOW; most changes are low-risk |
| lines_changed | 1.8 | Larger diffs correlate with higher defect density |
| files_changed | 1.2 | Cross-cutting changes have higher coordination risk |
| churn_ratio | 1.5 | Recently-modified code carries more regression risk |
| coverage_gap | 2.0 | Untested code is harder to validate |
| sensitive_paths | 2.5 | Security/payment/infra paths have outsized blast radius |

Features are log-scaled to [0, 1] before weighting (except churn_ratio and coverage_gap which are already ratios).

## Tier Boundaries

| Score Range | Tier | Approval Requirement |
|---|---|---|
| 0.75 – 1.00 | CRITICAL | Human approval + security review |
| 0.50 – 0.74 | HIGH | Human approval |
| 0.25 – 0.49 | MEDIUM | Peer review |
| 0.00 – 0.24 | LOW | Automated checks |

## Sensitive Path Patterns

Paths matching any of these patterns increase the `sensitive_paths` feature:

- `**/auth/**`, `**/security/**`, `**/*secret*`
- `**/migrations/**`
- `**/.github/workflows/**`, `**/Dockerfile`
- `**/pom.xml`, `**/package.json`
- `**/payment/**`, `**/billing/**`
- `**/iac/**`, `**/terraform/**`

## Fail-Safe

When a score cannot be computed (missing data, parse error), the default tier is **HIGH**.
