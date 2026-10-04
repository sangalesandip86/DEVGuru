# Performance Checklist (code level)


A performance finding is only a finding when tied to a number. For each item, state the input
size or call rate it depends on. If that number is not in the requirement, ADR, or Change Set,
raise a `QUESTION` (e.g., "Expected rows per tenant in `orders`?") instead of asserting impact.

| # | Check | What to look for | Needs number |
|---|---|---|---|
| 1 | **N+1 queries** | Query or remote call inside a loop over a collection | Collection size |
| 2 | **Unbounded result sets** | `SELECT` / list API without `LIMIT`/pagination | Table/row growth |
| 3 | **Missing index for new access path** | New `WHERE`/`ORDER BY`/`JOIN` column without index in migration | Table size, query rate |
| 4 | **Quadratic algorithms** | Nested loops over the same input, `list.contains` in a loop | n |
| 5 | **Blocking I/O on hot/async path** | Sync HTTP/disk/sleep in request handler or event loop | Request rate, p99 target |
| 6 | **Chatty remote calls** | Several sequential calls that could batch or parallelize | Latency budget |
| 7 | **Missing timeouts** | HTTP/DB/queue clients without explicit timeout | Upstream SLO |
| 8 | **Unbounded memory** | Loading whole files/tables into memory; caches without size/TTL | Data size |
| 9 | **Lock contention** | Coarse locks around I/O; `synchronized` on hot paths | Concurrency |
| 10 | **Allocation in tight loops** | String concat in loops, regex compile per call | Call rate |
| 11 | **Serialization overhead** | Repeated JSON encode/decode of the same object | Payload size, rate |
| 12 | **Retry storms** | Retries without backoff + jitter, or without a budget | Fleet size |
| 13 | **Cache correctness** | Cache key missing tenant/user/version dimension | — (correctness, always check) |
| 14 | **Logging volume** | Per-item logs in loops; logging full payloads | Request rate |

## Evidence hierarchy

1. Benchmark or profiler output attached to the Change Set → cite as FACT.
2. Perf baseline from `../../../testing/performance-testing/perf-baseline-tracker/` → FACT.
3. Complexity reasoning from code + a stated number → `RISK` with `INFERENCE` basis.
4. Complexity reasoning without a number → `QUESTION`, never a BLOCKER.

Escalate system-level concerns (capacity, partitioning, fan-out) to
`../../scale-readiness-reviewer/SKILL.md` rather than reviewing them here.
