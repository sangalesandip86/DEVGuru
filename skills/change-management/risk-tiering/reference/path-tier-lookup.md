# Phase 0 Path-Tier Lookup

Ships in Phase 0 so that nothing in Phase 1 is ever unable to compute a tier before the full
`compute_risk_tier` capability exists (§2 — closes the Phase 1/Phase 3 circularity).

## Files
- [`../path-tiers.json`](../path-tiers.json) — rules (glob → tier), docs-only patterns, default tier,
  diff-size cap. Policy values; overridable, tighten-only in repo overrides.
- [`../scripts/path_tier_lookup.py`](../scripts/path_tier_lookup.py) — the lookup (stdlib only).
- Control-file globs come from `skills/governance/default-permissions/reference/control-file-paths.json`;
  if it is missing or unreadable, an embedded fallback list is used (`control_files_source` in the
  output says which).

## Decision rule

| Input | Tier |
|---|---|
| No paths supplied, or config/git error | **HIGH** (`computed: false`, exit 3) — §5.3 fail-safe |
| Any control-file path | **CRITICAL** — overrides everything, including docs-only (e.g. `AGENTS.md`) |
| Path matches a rule | Rule's tier (highest if several) |
| Path matches only `docs_only` | LOW |
| Any other path | `default_tier` = MEDIUM — ordinary code is not assumed low-risk |
| Overall | Maximum across all paths |

`decompose_required` is set when file count or changed lines exceed `diff_size_cap` (§7); it does
not change the tier.

## Usage
```bash
python skills/change-management/risk-tiering/scripts/path_tier_lookup.py --git-base origin/main
git diff --name-only main | python .../path_tier_lookup.py --stdin --changed-lines 120
python .../path_tier_lookup.py services/payment/refund.py README.md
```

Output (abridged):
```json
{"tier": "HIGH", "computed": true, "reason_codes": ["SENSITIVE_PATH"],
 "paths": [{"path": "services/payment/refund.py", "tier": "HIGH",
            "matched": [{"rule": "payment", "tier": "HIGH", "patterns": ["**/payment/**"]}]}],
 "decompose_required": false, "control_files_source": ".../control-file-paths.json"}
```

## Story-type floors and importing (v3.1 §4.12)
- `--type-floor HIGH` adds `effective_tier = max(floor, path tier)` to the output.
- As a module (add `skills/change-management/risk-tiering/scripts` to `sys.path`):
  ```python
  from path_tier_lookup import compute_path_tier, effective_tier
  r = compute_path_tier(["services/payment/refund.py"], changed_lines=120)
  tier = effective_tier(type_floor, r["tier"], computed_tier)   # None entries ignored
  ```
  `compute_path_tier` never raises on bad config; it returns `HIGH` with `computed: False`.

## Tests
`python -m unittest discover -s skills/change-management/risk-tiering/tests`
