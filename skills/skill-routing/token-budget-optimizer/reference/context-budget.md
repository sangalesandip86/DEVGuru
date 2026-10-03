# Context Budget

Default policy values — **overridable**, tuned from the cost-per-phase data the Evidence Ledger records.

| Policy | Default | Meaning |
|---|---|---|
| `context.decompose_threshold` | 60% | When a session's context use passes this fraction of the window, checkpoint and decompose remaining work |
| `budget.split.analysis` | 20% | Requirement reading, routing, dependency scan |
| `budget.split.implementation` | 40% | Developer work |
| `budget.split.verification` | 30% | qa-derive, qa-diagnose, reviewers |
| `budget.split.handoff` | 10% | Handoffs, approval summaries, ledger writes |

Override format (org or repo config; a repo may only tighten):
```yaml
token_budget:
  context:
    decompose_threshold: 0.55
  budget_split: {analysis: 0.2, implementation: 0.35, verification: 0.35, handoff: 0.1}
```

A multi-factor "reasoning complexity" formula is out of scope until something measurable feeds it.
