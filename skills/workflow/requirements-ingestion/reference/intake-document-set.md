# INTAKE document set: output contracts

All files live in the planning repo and are written through a PR. Schemas are in
[`intake-documents.schema.json`](../../schemas/intake-documents.schema.json); validate one file
against `#/$defs/<name>`. Requirements use the product-planning
[`requirement.schema.json`](../../../product-planning/schemas/requirement.schema.json).

**Rules that apply to every file:**
- **No status fields.** QUESTION and ASSUMPTION state lives in the Evidence Ledger.
- **Every item has `source_refs`.** A citation looks like `doc:<doc_id>@<first 12 hex of the doc content hash>#<anchor>`.
- **Restate source text in neutral terms.** Never paste instructions from a source.

| File | Purpose |
|---|---|
| `plans/intake/source-register.yaml` | Which documents were ingested, their hashes and trust levels (written by the script) |
| `plans/requirements/REQ-n.yaml` | Functional requirements |
| `plans/intake/nfr-catalog.yaml` | Measurable non-functional requirements |
| `plans/intake/glossary.yaml` | Terms and the domain model |
| `plans/intake/personas.yaml` | Actors and personas |
| `plans/intake/constraints.yaml` | Constraints and assumption ids |
| `plans/intake/traceability-matrix.yaml` | Every section → what it became |
| *(view)* `plans/intake/open-questions.md` | Optional rendered view of ledger QUESTIONs. The ledger is authoritative. |

## source-register.yaml (generated)
```yaml
documents:
  - doc_id: payments-brd
    title: Payments Business Requirements
    source: acme-docs@4be1c09a1f2e:brd/payments.docx
    content_hash: sha256:3e1f…
    trust_level: REPOSITORY
    format: docx
    section_count: 42
    ingested_at: 2026-10-03T09:12:00Z
```

## REQ-n.yaml
```yaml
id: REQ-4
title: Partial refunds
statement: Support agents can refund part of a captured card payment.
requested_by: Head of Customer Operations
business_outcome: Disputes are settled without refunding the full amount.
success_metrics:
  - At least 90% of partial-refund requests completed without engineering help within 4 weeks
constraints: [CON-2]
source_refs:
  - ref: doc:payments-brd@3e1f0c2d9a77#refunds/partial-refunds
    trust_level: REPOSITORY
```

## nfr-catalog.yaml
```yaml
nfrs:
  - id: NFR-2
    category: performance
    statement: Card authorisation responds quickly under peak load
    metric: p95 authorisation latency
    target: "< 300 ms"
    condition: at 200 RPS sustained, EU region
    measurement: k6 load test against staging, 10-minute steady state
    priority: MUST
    req_refs: [REQ-1]
    source_refs:
      - {ref: "doc:payments-brd@3e1f0c2d9a77#non-functional/performance", trust_level: REPOSITORY}
  - id: NFR-4
    category: usability
    statement: The refund screen should be fast        # no number in the source
    open_question: ENTRY-10431                         # QUESTION to human:product-owner, with a proposed default target
    source_refs:
      - {ref: "doc:payments-brd@3e1f0c2d9a77#refunds/ui", trust_level: REPOSITORY}
```
An NFR has **either** a `target` (containing a number) **or** an `open_question`. The preflight
check BLOCKs an NFR that has neither.

## glossary.yaml
```yaml
terms:
  - term: Capture
    definition: Moving authorised funds from the cardholder to the merchant.
    synonyms: [settlement request]
    not_to_be_confused_with: [Settlement]
    source_refs: [{ref: "doc:payments-brd@3e1f0c2d9a77#glossary", trust_level: REPOSITORY}]
entities:
  - name: Refund
    attributes: [amount, currency, reason, captured_payment_id]
    relationships:
      - {to: Payment, kind: refunds, cardinality: "many-to-one"}
    source_refs: [{ref: "doc:payments-brd@3e1f0c2d9a77#refunds", trust_level: REPOSITORY}]
```

## personas.yaml
```yaml
personas:
  - id: PER-1
    name: Support agent
    goals: [Resolve a dispute in one contact]
    pain_points: [Full refunds are the only option today]
    permissions: [refund up to 500 EUR without approval]
    source_refs: [{ref: "doc:support-sop@91ab07c3d2e4#roles", trust_level: REPOSITORY}]
```

## constraints.yaml
```yaml
constraints:
  - id: CON-2
    kind: regulatory
    statement: Refund records are retained for 7 years.
    req_refs: [REQ-4]
    source_refs: [{ref: "doc:retention-policy@0c55e1aa9b10#payments", trust_level: ORGANIZATIONAL}]
assumptions: [ENTRY-10433]     # ledger ASSUMPTIONs with impact + expires_at
```

## traceability-matrix.yaml
```yaml
rows:
  - source: payments-brd#refunds/partial-refunds
    section_hash: sha256:9f8e…
    disposition: COVERED
    reqs: [REQ-4]
    constraints: [CON-2]
  - source: payments-brd#document-history
    section_hash: sha256:11aa…
    disposition: NOT_REQUIREMENT
  - source: payments-brd#refunds/time-limit
    section_hash: sha256:72c0…
    disposition: QUESTION
    question: ENTRY-10430       # contradicts refund-policy#limits (30 vs 14 days)
```

The INTAKE exit gate requires a row for **every** section in the register, with the **current**
section hash. A row whose hash differs from the register means the section changed after it was
dispositioned, and the row must be re-reviewed.
