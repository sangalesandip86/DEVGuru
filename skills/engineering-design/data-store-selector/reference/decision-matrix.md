# Data Store Decision Matrix

<!-- reconstructed: v2 source not provided; review -->

## Step 1 — Hard constraints (eliminate)

| Constraint | Eliminates |
|---|---|
| Multi-row/multi-entity ACID transactions required | Most key-value, wide-column, search engines as primary store |
| Ad hoc queries / joins across entities needed by product | Key-value, wide-column (without secondary tooling) |
| Strong read-after-write consistency on every read | Async-replicated reads, search indexes as source of truth |
| Single item > ~1 MB routinely | Most KV/document stores as blob holders → use object storage + pointer |
| Writes > ~10k/s sustained, single logical table | Single-primary relational without sharding plan |
| Data residency / compliance boundary | Any managed offering not available in required region |

## Step 2 — Fit by access pattern

| Store family | Strong fit | Weak fit | Example products (non-exhaustive) |
|---|---|---|---|
| **Relational** | Transactions, joins, evolving queries, integrity constraints; up to ~TBs and ~10k writes/s on one primary | Massive write fan-in, schemaless data | PostgreSQL, MySQL, SQL Server |
| **Document** | Aggregate-oriented reads (fetch whole object by id), flexible schema per item | Cross-document transactions, heavy joins | MongoDB, Couchbase, Firestore |
| **Key-value** | Lookup by key at very high QPS, sessions, caches, counters | Queries by non-key attributes | Redis, DynamoDB (KV usage), Memcached |
| **Wide-column** | Very high write throughput, time/partition-ordered reads, multi-region writes | Ad hoc queries; access patterns unknown upfront | Cassandra, ScyllaDB, Bigtable |
| **Search** | Full-text, faceting, relevance ranking, fuzzy matching | Source of truth; transactional updates | OpenSearch, Elasticsearch, Typesense |
| **Time-series** | Append-heavy metrics/events with time-range aggregates, downsampling, retention | Random updates | TimescaleDB, InfluxDB, Prometheus (metrics) |
| **Graph** | Multi-hop relationship traversal (≥3 hops) as the main query | Simple 1-hop relations (relational handles these) | Neo4j, Neptune |
| **Analytical / columnar** | Large scans and aggregates, BI | Low-latency point lookups, OLTP | BigQuery, Snowflake, ClickHouse, DuckDB |
| **Object storage** | Large blobs, files, data lake, cheap retention | Low-latency small-item queries | S3, GCS, Azure Blob |

## Step 3 — Weighted scoring (for the survivors)

Score 1–5; weights must be stated per decision (defaults shown).

| Criterion | Default weight | Notes |
|---|---|---|
| Fits top-3 access patterns by frequency | 30% | Use the numbers from the procedure |
| Already operated by the org (backups, monitoring, on-call) | 20% | Strong tie-breaker |
| Consistency model matches requirement | 15% | Per access pattern |
| Scale headroom at 24-month volume | 15% | Show the calculation |
| Team expertise | 10% | |
| Cost at projected volume | 10% | Storage + IO + ops time |

## Common outcomes

- **Default:** relational primary store. Add a cache or search index *derived* from it when a
  measured pattern requires it; keep the relational store as source of truth.
- **Polyglot persistence** needs a sync mechanism (CDC/outbox) and a reconciliation check — record both.
- **"We might need scale later"** is not a signal; write a "Revisit when" with a number.
