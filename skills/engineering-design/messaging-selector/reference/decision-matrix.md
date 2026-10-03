# Messaging Decision Matrix

<!-- reconstructed: v2 source not provided; review -->

## Step 1 — Sync or async?

| Situation | Choose |
|---|---|
| Caller needs the result to respond; callee p99 within caller's budget | Synchronous call (with timeout + retry budget) |
| Work takes > a few seconds, or caller doesn't need the result | Async job queue |
| Several independent consumers react to one fact | Pub/sub or log |
| Consumers need to replay history or rebuild state | Log/stream |
| Burst rate > downstream sustainable rate | Queue as buffer |

## Step 2 — Pattern

| Pattern | Semantics | Ordering | Replay | Fits |
|---|---|---|---|---|
| **Work queue** | Each message to one consumer; ack/delete | Usually none (FIFO variants per group) | No | Background jobs, task distribution |
| **Pub/sub (topic → subscriptions)** | Each subscriber gets a copy | Per-subscription, limited | Limited | Notifications, fan-out to a few services |
| **Log / stream** | Append-only, consumers track offsets | Per partition/key | Yes, within retention | Event sourcing, CDC, analytics, many consumers |
| **Outbox + relay** | DB write and event publish atomically | Per aggregate | Via log | Any "update DB and emit event" — avoids dual-write bugs |

## Step 3 — Broker

| Broker type | Throughput sweet spot | Strengths | Weaknesses | Examples |
|---|---|---|---|---|
| Managed simple queue | up to thousands msgs/s, scales out | Zero ops, DLQ built in | Limited ordering, no replay | SQS, Azure Queue, Cloud Tasks |
| Managed pub/sub | thousands–hundreds of thousands msgs/s | Fan-out, zero ops | Ordering/replay vary | SNS, Google Pub/Sub, Event Grid |
| Traditional broker | up to tens of thousands msgs/s per node | Routing, priorities, rich semantics | Ops burden, replay limited | RabbitMQ, ActiveMQ |
| Distributed log | 10k–millions msgs/s | Replay, ordering per partition, many consumers | Ops complexity, partition planning | Kafka, Redpanda, Kinesis, Event Hubs |
| DB-backed queue | < ~hundreds msgs/s | No new infra, transactional with app data | Polling load, limited scale | Postgres `SKIP LOCKED`, job libraries |

Rule: if volume is < ~100 msgs/s and you already run a relational DB, a DB-backed queue is
usually the right first step. Record the "Revisit when" threshold.

## Required design checklist

- [ ] Delivery semantics stated (at-least-once default; "exactly-once" claims require idempotent consumers anyway).
- [ ] Idempotency key defined and dedup window stated.
- [ ] Ordering scope (key) stated, or "none needed" stated.
- [ ] Retry policy: max attempts, backoff with jitter.
- [ ] DLQ: owner, alert threshold, redrive procedure.
- [ ] Consumer lag metric and alert.
- [ ] Schema versioning + compatibility direction recorded as a contract.
- [ ] Message size limit vs. max payload (large payloads → object storage + reference).
