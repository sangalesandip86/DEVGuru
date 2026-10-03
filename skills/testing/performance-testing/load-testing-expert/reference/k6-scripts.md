# k6 Script Patterns

<!-- reconstructed: v2 source not provided; review -->

## Open-model load test with SLO thresholds

```js
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const products = new SharedArray('products', () => JSON.parse(open('./data/products.json')));

export const options = {
  scenarios: {
    browse: {
      executor: 'ramping-arrival-rate',   // open model: arrivals don't wait for responses
      startRate: 10, timeUnit: '1s',
      preAllocatedVUs: 50, maxVUs: 500,
      stages: [
        { target: 200, duration: '5m' },  // ramp to expected peak (cite source of 200 rps)
        { target: 200, duration: '15m' }, // hold
        { target: 0, duration: '2m' },
      ],
      exec: 'browse',
    },
    checkout: {
      executor: 'constant-arrival-rate',
      rate: 20, timeUnit: '1s', duration: '22m',
      preAllocatedVUs: 20, maxVUs: 200,
      exec: 'checkout',
    },
  },
  thresholds: {
    'http_req_failed': ['rate<0.001'],
    'http_req_duration{scenario:browse}': ['p(95)<300', 'p(99)<800'],
    'http_req_duration{scenario:checkout}': ['p(95)<600'],
    'checks': ['rate>0.999'],
  },
};

const BASE = __ENV.BASE_URL;            // never hard-code; never default to production

export function browse() {
  const p = products[Math.floor(Math.random() * products.length)];
  const res = http.get(`${BASE}/products/${p.id}`, { tags: { name: 'GET /products/:id' } });
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function checkout() {
  const res = http.post(`${BASE}/orders`, JSON.stringify({ sku: 'TEST-SKU', qty: 1 }), {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${__ENV.TOKEN}` },
    tags: { name: 'POST /orders' },
  });
  check(res, { 'status 201': (r) => r.status === 201 });
}
```

## Patterns
- **Tag URLs with a `name`** so dynamic paths aggregate into one metric (`/products/:id`), otherwise
  thresholds and summaries explode into thousands of series.
- **Stress**: `ramping-arrival-rate` with stages beyond peak (1×, 1.5×, 2×, 3×) and
  `abortOnFail` thresholds to stop once error rate crosses the limit.
- **Soak**: `constant-arrival-rate` at expected load for 2–8h; watch memory, connections, queue depth server-side.
- **Spike**: stages `{target: peak*5, duration: '30s'}` then back down; measure recovery time.
- **Data**: `SharedArray` for large inputs (loaded once, shared read-only across VUs).
- **Secrets** via `__ENV` from the CI secret store, never in the script.

## Running and recording evidence
```bash
k6 run --summary-export=results/summary.json --out json=results/raw.json \
  -e BASE_URL=$STAGING_URL -e TOKEN=$TOKEN load/checkout.js
```
- Exit code 99 means a threshold failed — CI treats it as a failed check.
- `summary.json` is what perf-baseline-tracker compares against the stored baseline.
- For distributed runs use the k6 Operator on Kubernetes or Grafana Cloud k6; record generator count.
