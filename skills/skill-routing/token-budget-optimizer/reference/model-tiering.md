# Model Tiering

<!-- reconstructed: v2 source not provided; review -->

Two tiers only — a capability matrix is deferred (§2) because model capabilities change every release.

| Tier | Use for |
|---|---|
| **fast/cheap** | Phase 1 routing, file search, summarizing logs, formatting handoffs, scanning output triage |
| **strong** | Implementation, design, security review, qa-derive test design, qa-diagnose root cause, any HIGH/CRITICAL work |

Rules:
- HIGH/CRITICAL tasks use the strong tier for every judgment step. Budget pressure never downgrades them.
- Reviewer diversity (§4.7): for HIGH/CRITICAL, at least one reviewer runs on a different model
  family than the implementing developer, or is a deterministic tool.
- Record `model_id` on every AGENT ledger entry.
- Defaults are overridable policy values, tuned from ledger cost-per-phase data.
