# Risk Matrix


Four tiers with fail-safe defaults. Multi-dimensional weighted scoring is deferred (§2) until
observability data shows which dimensions matter.

## Tier definitions and gates (§5.4)

| Tier | Typical change | Gates |
|---|---|---|
| LOW | README / docs, comments, non-shipped assets | developer + docs check |
| MEDIUM | Internal refactor, non-sensitive feature code, dependency bump | developer + tests (`VERIFIED`) + code-reviewer (`REVIEWED`) |
| HIGH | Public API change, auth/payment/migration paths, IaC, agent/prompt code | architect + contract analysis + security-reviewer + code-reviewer; reviewer-diversity rule |
| CRITICAL | Payment schema migration, control-file change, irreversible data change | product-owner + architect + security-reviewer + staged rollout + human release approval; reviewer-diversity rule |

## Factors (highest factor sets the tier)

| Factor | LOW | MEDIUM | HIGH | CRITICAL |
|---|---|---|---|---|
| Sensitive path (path-tiers.json) | docs only | default code | sensitive rule match | control file |
| Blast radius | none at runtime | one service, internal | multiple consumers / public API | cross-system, customer money or data |
| Data sensitivity | none | internal data | PII, credentials, auth state | payment data, irreversible deletion |
| Reversibility | trivial revert | revert + redeploy | needs data fix / coordinated rollback | not reversible |
| Contract exposure | none | internal contract, compatible | external or breaking-compatible change | breaking change to a deployed consumer |
| Repositories | 1 | 1 | ≥2 | ≥2 with ordering constraints |

## Story-type tier floors (v3.1 §4.12)

Each story type in `skills/product-planning/policies/story-types.yaml` may set a floor:

| Type | Floor |
|---|---|
| `API_CONTRACT`, `DATA_MIGRATION`, `SECURITY_STORY` | HIGH |
| `INFRASTRUCTURE` | MEDIUM |
| `DOCUMENTATION` | LOW |
| all other types | none |

**Effective tier = max(type floor, path tier (Phase 0 lookup), computed tier (§4.5)).**
A type can raise the tier, never lower it: a `DOCUMENTATION` story whose diff touches
`services/payment/` is HIGH, and the mismatch between declared type and actual diff is a scope
violation (`grounding/agent-failure-modes` → ESCALATE). The actual diff decides the tier.
In code: `path_tier_lookup.effective_tier(type_floor, path_tier, computed_tier)`; on the CLI,
`--type-floor HIGH` adds `effective_tier` to the output. When a Change Set implements several
stories, the floor is the highest floor among its `story_refs[]`.

## Fail-safe defaults (§5.3)

| Situation | Default |
|---|---|
| Tier cannot be computed | HIGH |
| Two roles disagree | Higher assessment wins |
| Agent uncertain, named reason code | +1 level, exactly |
| Dependency not found by static analysis | UNRESOLVED (→ `UNRESOLVED_DEPENDENCY` escalation) |
| Compatibility unknown | INCOMPATIBLE (→ `COMPATIBILITY_UNKNOWN` escalation) |

## Change size
Above the configured diff-size cap (`path-tiers.json` → `diff_size_cap`), decompose before
implementing (§7). Large AI-generated diffs are hard to review and drive rework.
