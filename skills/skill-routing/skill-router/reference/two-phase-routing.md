# Two-Phase Routing

## Phase 1 — Coarse routing
- Inputs: requirement text, repo names, changed or mentioned file paths.
- Method: keyword and glob matching against [scope-matrix.md](scope-matrix.md).
- Properties: cheap, deterministic, always includes the always-mandatory set, may over-include.
- Output: initial skill set + initial tier (Phase 0 path lookup; `HIGH` if not computable).

## Phase 2 — Refined routing
Runs after initial analysis (risk tier, dependency scan, file reads).
- **May ADD** contextual/advisory skills.
- **May ADD mandatory bindings** by re-running the mandatory computation against its deeper
  understanding of the task. Example: "update the fee calculation in `BillingAdjuster.java`" has
  no literal `payment` keyword but is payment-domain code → the payment bindings apply.
- **May NOT remove** any binding skill Phase 1 included.
- **May raise** the tier; never lowers it. Only an authenticated human downgrade can, and it is
  logged (`change-management/risk-tiering`).

## Near-miss logging
When Phase 2 adds a mandatory binding Phase 1 missed:
1. Apply the binding retroactively for the remainder of the task. Work already done under the
   weaker binding is re-checked by the newly bound skills/roles.
2. Write a `DECISION` ledger entry citing the evidence (file:line) that triggered the domain call.
3. `record_incident`:
   ```yaml
   trigger: routing-near-miss
   signal_source: AGENT
   context:
     phase1_matches: [...]
     phase2_trigger: payment-domain
     evidence: ["src/BillingAdjuster.java:42"]
   hypothesis: "keyword list lacks 'fee'/'adjuster' for payment domain"   # INFERENCE, unconfirmed
   proposal: "add keywords to scope-matrix payment row"                  # PROPOSAL
   ```
4. `self-improvement/improvement-review` aggregates near-misses. Crossing its pattern threshold
   produces a candidate scope-matrix revision, which goes `REVIEWED` → `APPROVED` like any change.

## Re-routing triggers
Re-run Phase 2 when the changed-file set grows, a new repo enters scope, the tier changes, or a
handoff introduces a new domain.
