# Scaling Playbook

<!-- reconstructed: v2 source not provided; review -->

Apply steps in order of cost. Each step lists the signal that justifies it — cite that
signal (metric, load test, capacity plan) as the source. Without a signal, the step is
premature; record it as a "Revisit when" trigger instead.

## Ladder (cheapest first)

| Step | Signal that justifies it | Typical gain | Cost / risk |
|---|---|---|---|
| 1. Measure | No profile/metrics yet | Finds the real bottleneck | Low |
| 2. Fix the query/algorithm | Slow query log, profiler hot spot | 10–100× on the hot path | Low |
| 3. Add indexes | Seq scans on large tables in hot queries | Large for reads | Write amplification, migration lock time |
| 4. Vertical scale | CPU/memory saturation, headroom <30% | 2–4× | Cost; ceiling |
| 5. Cache (read-through, TTL) | Read:write ≥ 10:1, tolerable staleness stated | 5–50× read capacity | Invalidation bugs, stampedes |
| 6. Horizontal stateless scale | App tier saturated, state externalized | Near-linear | Session/state externalization |
| 7. Async offload (queue) | Work not needed in the response; bursty load | Smooths peaks | Eventual consistency, retries, DLQ |
| 8. Read replicas | Read-heavy DB; replica lag tolerance stated | Read capacity ×N | Stale reads; lag monitoring |
| 9. Connection pooling / bulkheads | Connection exhaustion, noisy neighbors | Stability | Tuning |
| 10. Partition / shard | Single-primary write limit approached; data > single node | Write capacity ×N | Cross-shard queries, rebalancing — hard to undo |
| 11. Multi-region | Latency to distant users, regional availability requirement | Latency, availability | Consistency, cost, ops — hardest to undo |

## Back-of-envelope reference numbers

Use these only to sanity-check; replace with measured values from the target environment.

| Quantity | Rough order |
|---|---|
| Single well-indexed relational primary, simple writes | 1k–10k writes/s |
| Single relational primary, simple indexed reads | 10k–50k reads/s |
| In-memory cache node | 100k+ ops/s |
| Same-region network round trip | ~0.5–1 ms |
| Cross-region round trip | 50–150 ms |
| Single partition of a log-based broker | ~10 MB/s |

## Capacity estimate template

```
Peak QPS = daily requests × peak factor / 86,400        (peak factor: state source, else QUESTION)
Storage 24 mo = rows/day × bytes/row × 730 × (1 + index overhead ~0.5–1.0)
Headroom = (capacity − peak) / capacity                  (target ≥ 30%)
```

## Reversibility rule

Steps 10–11 are effectively one-way. Recommending them requires: measured signal, an explicit
"steps 2–9 exhausted or inapplicable" justification, and HIGH tier minimum.
