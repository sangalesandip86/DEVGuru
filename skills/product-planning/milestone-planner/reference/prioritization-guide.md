# Prioritization guide (advisory)

The planner **proposes** an order. A human decides it. The proposal is a PROPOSAL ledger
entry. The human's choice is a DECISION entry recorded by that human, which may differ from
the proposal. Every override counts toward the human-override rate (plan §7), and that rate
is worth watching.

## Default method: WSJF with sourced inputs

`WSJF = Cost of Delay / Job Size`, where
`Cost of Delay = User/Business Value + Time Criticality + Risk Reduction/Opportunity Enablement`.

| Input | Scale | Must be sourced from |
|---|---|---|
| User/business value | 1, 2, 3, 5, 8, 13, 20 (relative within the candidate set) | the requirement's `business_outcome` / `success_metrics`, or a stakeholder statement (ledger ENTRY) |
| Time criticality | same scale | a cited date, contract, regulation or market event |
| Risk reduction / opportunity enablement | same scale | the dependency map (what this unblocks), or a recorded RISK |
| Job size | derived from story sizes (XS=1, S=2, M=5) | the stories' `size` and `size_basis` |

Rules:
1. **No unsourced input.** If an input can't be sourced, mark it `QUESTION` and leave it out of the score. Don't guess a number. A score with missing inputs is reported as incomplete.
2. **Relative, within one candidate set.** WSJF numbers are not comparable across sets or over time.
3. **Show the inputs, not just the rank.** Present the proposal in [human-review-format](../../../grounding/human-review-format/SKILL.md): a table of items × inputs × sources, the resulting order, and what would change the order.
4. **Hard constraints come first.** Dependencies (an UNRESOLVED dependency means the dependent can't go first), entry criteria and fixed dates order the work before WSJF does. WSJF only orders what the constraints leave free.
5. **Risk-first for HIGH and CRITICAL tiers.** Schedule SPIKEs and the riskiest slices early, even when their WSJF is lower. Present this as an explicit deviation with its reason.

## Proposal format

```yaml
classification: PROPOSAL
content: Proposed order for MS-1 candidates
items:
  - story: ST-3   # spike
    order: 1
    reason: entry criterion of MS-1; unblocks ST-2 and ST-4 (dependency map)
  - story: ST-2
    order: 2
    wsjf: {value: 8, time_criticality: 5, risk_reduction: 8, size: 5, score: 4.2}
    sources: [REQ-1.success_metrics[0], ENTRY-512 (desk head: pilot on 2026-11-20)]
  - story: ST-1
    order: 3
    wsjf: {value: 13, time_criticality: 5, risk_reduction: 2, size: 2, score: 10.0}
    note: higher WSJF but depends on ST-2 (hard constraint)
incomplete_inputs: []
```

## What this guide does not do
- **Capacity or iteration planning.** Teams own their commitments. The platform reads the iteration from the tracker.
- **Cross-team portfolio prioritization.** That is deferred until more than one team shares requirements across systems (plan §2).
