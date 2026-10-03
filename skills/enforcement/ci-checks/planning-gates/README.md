# Planning gates

These CI checks enforce the Product Planning layer (plan v3.1 §4.12, §5.6). The skills in
[`skills/product-planning/`](../../../product-planning/) explain the rules to agents. These
gates enforce them. Agents have no tool that sets a story's status. READY, DONE and ACCEPTED
exist only as outputs of these gates, which run as SYSTEM CI jobs.

| Script | Runs on | Decides |
|---|---|---|
| `plan_lint.py` | every PR touching `plans/` | Checks schemas (no `status` field), file names, referential integrity, the AC standard and ACCEPTED_RISK owners. Warns on layer-shaped milestones and on unquantified NFRs. **AC freeze** → `REQUIRES_REFINING`. |
| `readiness_gate.py` | merge to the plans branch; re-run when new evidence lands | Definition of Ready → `READY` / `NOT_READY` |
| `ac_coverage.py` | every CI test run of an implementing repo | Maps passing tests to AC IDs (`ST-n/AC-n`) |
| `completion_gate.py` | after a linked Change Set merges, or when evidence changes | Definition of Done → `NOT_DONE` / `DONE` / `ACCEPTED` |

Shared modules:
- `planning_lib.py`: policy evaluation, the structural check functions, tier computation, and a JSON-Schema subset validator.
- `ac_hash.py`: the canonical AC hash.
- `minyaml.py`: the YAML-subset loader.

All of them use the standard library only.

## Authority rules the code enforces

- **STRUCTURAL items** are deterministic functions over plan files and SYSTEM-exported evidence. They are listed in `planning_lib.STRUCTURAL_CHECKS`, and each policy item names one through `function:`.
- **JUDGMENT items** are satisfied *only* by a record with `lifecycle_state: REVIEWED` and `verdict: ACCEPT`. The record must come from an `AGENT` authenticated as the named role, or from a `HUMAN`:
  - A `SYSTEM` record never counts, and neither does any `VERIFIED` record, whatever it claims.
  - A `REJECT` from the role yields `REJECTED`, and only a human lifts it (§4.7).
  - When the item has `pin_ac_hash: true`, the review must carry the story's *current* AC hash, so a review taken before an AC edit stops counting.
- **APPROVAL items** need an approval event with `actor_type: HUMAN` naming the policy's `approver`.
- **Effective tier** is `max(type floor, path tier of affected_paths, declared risk_tier)`:
  - The path tier comes from [`path_tier_lookup.py`](../../../change-management/risk-tiering/scripts/path_tier_lookup.py).
  - Nothing can lower the tier.
  - If no input yields a tier, it is HIGH (§5.3).
- **Scope check at DONE:** if the actual diff's path tier exceeds the planned tier, `within_scope` FAILs. The story was misdeclared and must be re-tiered.

## Evidence export format (`--evidence`)

The CI job builds this file from the Evidence Ledger and from forge events, acting as SYSTEM. An agent never produces it.

```json
{
  "reviews":   [{"story": "ST-1", "item": "qa_testability", "role": "qa-derive", "actor_type": "AGENT",
                 "lifecycle_state": "REVIEWED", "verdict": "ACCEPT", "ac_hash": "sha256:…",
                 "ac": "ST-1/AC-4 (manual_ac_verified only)", "entry_id": "ENTRY-…"}],
  "approvals": [{"story": "ST-2", "item": "scope_approval", "approver": "human:product-owner", "actor_type": "HUMAN"}],
  "questions": [{"id": "ENTRY-…", "story": "ST-1", "state": "OPEN|ANSWERED|EXPIRED", "blocking": true}],
  "assumptions": [{"id": "ENTRY-…", "story": "ST-1", "impact": "LOW|MEDIUM|HIGH", "expires_at": "ISO-8601"}],
  "readiness": {"ST-1": {"status": "READY|IN_PROGRESS|…", "ac_hash": "sha256:…"}},
  "change_sets": [{"id": "CS-11", "story_refs": ["ST-1"], "status": "INTEGRATED", "changed_paths": ["…"]}],
  "gates":     [{"change_set": "CS-11", "gate": "ci|unit-tests|sast|sca|secret-scan|accessibility|contract-compatibility|rollback-test|staged-rollout",
                 "result": "VERIFIED", "actor_type": "SYSTEM"}],
  "decisions": [{"story": "ST-3", "adr_ref": "repo@sha:docs/adr/….md"}],
  "ac_coverage": "optional: output of ac_coverage.py"
}
```

In Phase 1 (forge-native), a Change Set's `story_refs` come from the PR body line `Implements: ST-101`.

## Exit codes

| Script | 0 | 1 | 2 | 4 |
|---|---|---|---|---|
| plan_lint | clean | errors | usage | AC freeze violations (only with `--fail-on-freeze`) |
| readiness_gate | READY | NOT_READY | usage/input | — |
| completion_gate | DONE / ACCEPTED | NOT_DONE | usage/input | — |
| ac_coverage | report written | — | usage/input | — |

## Running

```bash
G=skills/enforcement/ci-checks/planning-gates
python $G/plan_lint.py examples/plans --readiness examples/plans/evidence/evidence.json
python $G/readiness_gate.py --plans examples/plans --story ST-2 --evidence examples/plans/evidence/evidence.json
python $G/ac_coverage.py --tests examples/plans/evidence/tests --junit examples/plans/evidence/junit.xml --plans examples/plans --story ST-1 > cov.json
python $G/completion_gate.py --plans examples/plans --story ST-1 --evidence examples/plans/evidence/evidence.json --coverage cov.json
python -m unittest discover -s $G/tests -v
```

See [`workflow.example.yml`](workflow.example.yml) for the GitHub Actions wiring. It includes
the tracker-projection job, which is the only writer to the tracker.

> **Not built yet.** The workflow calls three `ledger_cli.py` subcommands that don't exist yet:
> `export-planning-evidence`, `record-planning-status` and `ingest-ac-coverage`. It also calls
> `tools/tracker_projection.py`, which doesn't exist either. They are sketched in the workflow
> to show where SYSTEM-identity steps sit. Until they are built, produce the evidence file by
> hand, as in `examples/plans/evidence/evidence.json`.

## Design notes

- **YAML subset.** Plan files and policies are reviewed by humans in PRs, so they are YAML. The gates must stay stdlib-only, so `minyaml.py` implements the subset the schemas need. Anything outside the subset (anchors, tags, multi-line flow) raises an error rather than being misread. A plain JSON document is also accepted.
- **Phase 2.** The `work_planning` module of the `adlc` MCP server is planned to import `planning_lib` and expose `evaluate_readiness` / `evaluate_done` as read-only dry-run tools. Status changes stay SYSTEM-only (`ingest_plan_commit`).
