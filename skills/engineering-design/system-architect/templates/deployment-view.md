# Deployment view

| Environment | Region(s) | Residency constraint | Scaling unit | Notes |
|---|---|---|---|---|
| staging | eu-west-1 | CON-3 (EU only) | 2 pods | Shared staging: CI-run tests only |
| production | eu-west-1, eu-central-1 | CON-3 | HPA 3–20 pods on CPU 60% | |

## Rollout
- Strategy: canary 5% → 25% → 100% with automatic rollback on SLO burn (staged rollout is required for CRITICAL, §5.4).
- Feature flags: per refund type.
- Migrations: expand → migrate → contract. Rollback is tested (DATA_MIGRATION DoD).
