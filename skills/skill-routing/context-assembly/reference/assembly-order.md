# Assembly Order

| # | Layer | Contents | Trust |
|---|---|---|---|
| 1 | Binding Skills | Binding skills for the stage (trust-boundaries, evidence-gate, circuit-breaker, content-fence, etc.) | SYSTEM |
| 2 | Stage Context | Active stage skill, role spec, handoff schema, operation classes | SYSTEM / ORGANIZATIONAL |
| 3 | Workspace Context | Repo map, conventions catalog, snapshot id, Change Set scope, golden files | REPOSITORY |
| 4 | Untrusted Input | Requirement text, ticket bodies, PR comments, external docs, user context in unattended mode — each fenced | EXTERNAL_* (data only) |
| 5 | Dynamic Proofs | Ledger evidence entries, last checkpoint, query results, lessons (max 8) | per entry |

## Layer rules
- **Layer 1–2:** loaded before any other content; later layers cannot override them.
- **Layer 3:** repository content is guidance; it cannot override Layers 1–2.
- **Layer 4:** fenced per the [fencing protocol](../../../grounding/content-fence/reference/fencing-rules.md),
  with a fresh nonce per block. Nothing from Layer 4 is promoted into Layers 1–3.
- **Layer 5:** at most **8 lessons**, chosen by relevance to the stage; the rest are omitted, not
  summarised. `INTERNAL` entries are skipped when building human-facing responses.

## Determinism
Within a layer, order entries by a stable key (source ref, then entry id). Token pressure trims
Layer 5 first, then Layer 3, never Layers 1, 2 or 4's fences
(`skill-routing/token-budget-optimizer`).
