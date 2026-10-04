---
name: risk-tiering
description: Compute a Change Set risk tier (LOW/MEDIUM/HIGH/CRITICAL) for gates and approvals. Use at creation and when scope changes.
metadata:
  group: change-management
  phase: 0
  binding: true
  plan-ref: "§2 Phase 0, §4.5, §5.3, §5.4, §7"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: [app]
---

# Risk Tiering

## Purpose
Scale process to risk: a README change and a payment-schema migration must not pass the same gates.
The tier selects gates (§5.4) and human approvals
([../change-set/reference/approval-matrix.md](../change-set/reference/approval-matrix.md)).

Two implementations, by phase:
- **Phase 0 — path lookup** (ships first, so nothing in Phase 1 is ever unable to compute a tier):
  `scripts/path_tier_lookup.py` + `path-tiers.json`. See [path-tier-lookup.md](reference/path-tier-lookup.md).
- **Phase 2 — full capability:** `mcp:adlc.compute_risk_tier` in the change_management module of
  the adlc MCP server (plan's Server 2), adding reason-code-gated escalation, dependency and
  contract inputs, and downgrade tracking.

## When this applies
- Creating a Change Set or opening a PR.
- The changed-file set, repository set, or dependency picture changes.
- Phase 2 routing finds a sensitive domain the path lookup did not.
- The agent is uncertain in one of the named reason-code situations.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Cross-cutting: tiers are computed at PLAN (from story type and declared paths) and recomputed at IMPLEMENT (from the actual diff).

- **Inputs:** changed or declared paths, story type, reason codes.
- **BACKFILL:** none — if inputs are missing the tier is HIGH (fail-safe), never skipped.
- **Repo roles:** `app` (paths to classify); control-file paths come from governance.

## Procedure
1. Run the path lookup on the changed paths:
   `python skills/change-management/risk-tiering/scripts/path_tier_lookup.py --git-base origin/main`
   (or pass paths / `--stdin`). Exit code 3 means the tier fell back to `HIGH`.
2. Apply the story-type floor (v3.1 §4.12): effective tier = max(type floor, path tier, computed
   tier). Types raise, never lower; see [risk-matrix.md](reference/risk-matrix.md#story-type-tier-floors-v31-412).
   Importers (e.g. `product-planning` `readiness_gate.py`) call `compute_path_tier()` and
   `effective_tier()` from `scripts/path_tier_lookup.py` directly.
3. If `decompose_required` is true, decompose the work into smaller tasks before implementing (§7).
4. Combine with [risk-matrix.md](reference/risk-matrix.md) factors (blast radius, data sensitivity,
   reversibility, contract exposure). Highest assessment wins; two roles disagreeing → higher wins.
5. Escalate by **exactly one level** only for a reason code in
   [escalation-reason-codes.md](reference/escalation-reason-codes.md). Never escalate by more than
   one, never for general unease.
6. Never lower a tier yourself. Only an authenticated human may downgrade, and every downgrade is logged.
7. Any control-file path → `CRITICAL`, regardless of everything else.

## Outputs
- `DECISION` entry: tier, matched rules, reason codes, script output as source.
- `RISK` entry for each escalation, with its reason code.
- Change Set `risk_tier` and `risk_tier_history[]` updated.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.

- Phase 0: the path lookup is deterministic; CI can run it and require the PR's labelled tier to be
  ≥ the computed tier. Control-file CRITICAL is enforced by managed settings + `PreToolUse` hook (§5.6).
- Phase 2: `compute_risk_tier` applies escalation rules server-side; downgrades require an
  authenticated human caller.
- Agent judgment of domain (Phase 2 routing) is guideline-level until reflected in the server call.

## References
- [reference/risk-matrix.md](reference/risk-matrix.md)
- [reference/escalation-reason-codes.md](reference/escalation-reason-codes.md)
- [reference/path-tier-lookup.md](reference/path-tier-lookup.md)
- [path-tiers.json](path-tiers.json) · [scripts/path_tier_lookup.py](scripts/path_tier_lookup.py)
- [../../skill-routing/skill-router/reference/scope-matrix.md](../../skill-routing/skill-router/reference/scope-matrix.md)
- [../../governance/autonomy-gating/SKILL.md](../../governance/autonomy-gating/SKILL.md)
