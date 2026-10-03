# JMeter Script Patterns

<!-- reconstructed: v2 source not provided; review -->

Use JMeter when the team already has `.jmx` plans, needs protocols k6 lacks out of the box (JMS, JDBC,
LDAP, FTP), or uses a vendor platform built on it. Otherwise prefer k6 for code-reviewable scripts.

## Plan structure
```
Test Plan  (user-defined variables: BASE_HOST, PROTOCOL — overridable via -J)
├── HTTP Request Defaults        (${__P(host)}, timeouts set explicitly)
├── HTTP Header Manager          (Content-Type, Authorization: Bearer ${__P(token)})
├── CSV Data Set Config          (users.csv, recycle=false, stopThread=true, sharing=all threads)
├── Concurrency Thread Group / Arrivals Thread Group   (JMeter Plugins — open-model load)
│   ├── Transaction Controller "Browse"
│   │   ├── HTTP Request GET /products/${productId}
│   │   └── Response Assertion (code 200) + JSON Assertion
│   ├── Transaction Controller "Checkout"
│   │   ├── HTTP Request POST /orders
│   │   ├── JSON Extractor  orderId ← $.id
│   │   └── Duration Assertion (≤ 600 ms)
│   └── Constant Throughput / Throughput Shaping Timer (target RPS)
└── (no View Results Tree / GUI listeners in CI)
```

## Rules
- **Parameterize with properties**: `${__P(host,localhost)}`, set on the command line with `-Jhost=...`.
  Secrets come from CI as `-Jtoken=$TOKEN`, never stored in the `.jmx`.
- **Open model**: plain Thread Groups are closed-model (fixed users); use Arrivals/Concurrency Thread
  Group or a throughput shaping timer to hold a target arrival rate.
- **Assertions on every sampler** that matters; a 200 with an error page is a failure.
- **No GUI listeners in load runs** — they consume generator memory and skew results.
- **Correlation**: extract dynamic values (CSRF tokens, ids) with JSON/Regex extractors; don't replay recorded values.
- Keep `.jmx` diffs reviewable: one logical change per commit; consider generating plans with
  `jmeter-java-dsl` if XML diffs become unmanageable.

## Running and recording evidence
```bash
jmeter -n -t load/checkout.jmx -Jhost=$STAGING_HOST -Jtoken=$TOKEN \
  -l results/results.jtl -e -o results/html-report
```
- `-n` non-GUI mode is mandatory in CI.
- JMeter doesn't fail the process on SLO breaches by itself: add a post-step that parses `results.jtl`
  (or `statistics.json` from the HTML report) and exits non-zero when p95/error-rate thresholds are
  exceeded, so CI produces deterministic pass/fail evidence. The Taurus (`bzt`) wrapper offers
  `passfail` criteria for the same purpose.
- Distributed mode (`-R host1,host2`) — record generator count and versions in the evidence.
