# Caching Strategy

<!-- reconstructed: v2 source not provided; review -->

- Order prompts stable-first: platform policy → binding skills → role definition → repo guidance → task.
  Stable prefixes cache well across tasks.
- Load skill `reference/` files on demand, after the cached prefix.
- Cache read-only analysis results (dependency scans, path-tier lookups) keyed by `snapshot_id`.
  A new snapshot invalidates them; never reuse results across snapshots.
- Never cache human approvals, VERIFIED status, or forge state — always re-read from the server.
