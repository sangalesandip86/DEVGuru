# Worked run examples

Each example shows the request, the parsed range, the preflight outcome, what each stage
produces, and where the run stops. Paths assume a planning repo `acme-plans` and an app repo
`payments-svc`. With a single repo, both resolve to the same repo and `plans/` lives inside it.

---

## 1. Requirement documents → architecture → plan (the primary entry)
> "Here are our requirement docs in `docs/requirements/`. Ingest them, create everything that
> follows, and go through architecture and planning."

- **Range:** INTAKE → PLAN, with `--adopt source-doc=docs/requirements/`.
- **Workspace:** `planning` FOUND (single-repo default). If the repo is MISSING, the resolver
  offers `--init-local planning ../acme-plans`.
- **Preflight INTAKE:** `source-doc` ADOPT. Everything else is produced by the run.

**INTAKE**
1. `ingest_documents.py docs/requirements/ --out .adlc/ingest --register-out plans/intake/source-register.yaml`
2. The agent writes the INTAKE document set. Every item cites a section anchor
   (`doc:payments-brd@3e1f…#refunds/partial-refunds`):
   - `REQ-1…REQ-9`
   - `nfr-catalog.yaml`: NFR-4 "fast" has no number, so it gets an `open_question` QUESTION to the PO
   - `glossary.yaml`
   - `personas.yaml`
   - `constraints.yaml`
   - `traceability-matrix.yaml`
3. Contradiction: the BRD says refunds within 30 days, but the policy doc says 14. That becomes one
   **blocking** QUESTION citing both anchors.
4. Gate: `plan_lint` passes, intake coverage passes (every section is dispositioned), and the
   blocking QUESTION is still open. The run stops with **ASK_PENDING**.

After the PO answers:

**ARCHITECTURE** (resumed). The system is greenfield, so the architecture package establishes standards:
- C4 L1/L2;
- `nfr-tactics.yaml` (NFR-2 "p95 < 300 ms at 200 RPS" maps to caching plus an async ledger write);
- a STRIDE threat model;
- `service-map.yaml` with 2 services, which becomes `adlc.workspace.yaml`;
- ADR-1 (stack) and ADR-2 (lint/format/conformance baseline).
- The service map calls for a new `payments-svc` repo, so the agent writes `repo-request.yaml` and a human creates the repo.
- Gate: architect REVIEWED, then `human:tech-lead` APPROVAL (the tier is HIGH because payments is a sensitive path).

**PLAN**
- EPIC-1 and EPIC-2, cut along the service boundaries.
- ST-1…ST-11 with AC.
- MS-1 "first refund end-to-end".
- `readiness_gate` runs per story: 8 are READY, and 3 are NOT_READY because the developer feasibility judgment is missing.
- The run stops with **END_REACHED**. The checkpoint lists the 3 stories and says: "resume from PLAN to refine ST-4, ST-9, ST-10".

---

## 2. Jira backlog → implement ST-40
> "We track work in Jira. Here's the export. Implement PAY-212."

- **Range:** IMPLEMENT → REVIEW (default end), with `--adopt story=jira-export.json`.
- **Preflight:** `ready-story` ADOPT. `conventions-catalog` BACKFILL, because this is an existing
  repo with no catalog.
- **Adoption:** `import_tracker.py --format jira-json` stages `plans/inbox/jira-pay-212.yaml`
  (`suggested_story_type: API_CONTRACT`, based on the `api` label).
- **Promotion:** story-writer promotes the item to `ST-40.yaml` and rewrites its AC to the standard.
- **Re-check:** preflight for ST-40 returns `ready-story` BLOCK. The type floor is HIGH, and the DoR
  needs the qa-derive testability and architect judgments.
- **Backfill:** the conductor proposes **BACKFILL PLAN (refinement only)** and then DESIGN, because
  tier HIGH requires a test design. It writes no code first.
- **Conventions:** `convention_scan.py --repo payments-svc --target src/payments/refunds` runs, and
  the catalog is now SATISFIED.
- **Stages:** the run continues through DESIGN → IMPLEMENT → TEST → REVIEW.
- **Stop:** INTEGRATE is observed, so the run stops with **OBSERVED_STAGE**: "awaiting merge of PR #881".

---

## 3. Tests for a legacy service (characterization)
> "Write tests for `billing-legacy`. There are no stories or docs."

- **Range:** TEST → TEST.
- **Preflight:** `test-design` ASK, with two options: (a) characterization tests of current
  behaviour, or (b) BACKFILL PLAN + DESIGN, writing AC first.
- **User chooses (a):** the conductor re-runs preflight with `--mode characterization`, and the result is SATISFIED.
- **test-engineer:**
  - runs repo discovery and picks mode B (convention mirror) or C (greenfield, which is its own story);
  - tags every test `characterization`;
  - records an ASSUMPTION: "current behaviour of billing-legacy@9ac1… is intended".
- **Exit gate:**
  - integrity guard and the flake gate apply;
  - `ac_coverage` does **not** count these tests;
  - no story becomes VERIFIED from them.
- **Stop:** END_REACHED. The checkpoint suggests writing AC later so the tests can graduate into AC-traced tests.

---

## 4. Only plan an epic
> "Only plan EPIC-3. Don't write code."

- **Range:** PLAN → PLAN.
- **Preflight:** `requirement` SATISFIED. `architecture-package` is checked against the effective
  tier: for MEDIUM or above it is required, and here it is present and REVIEWED.
- **Run:** epic-decomposer, story-writer, then refinement (three amigos), then milestone-planner.
- **Gate:** `readiness_gate` per story.
- **Stop:** the run ends at PLAN with END_REACHED. The checkpoint lists the READY and NOT_READY stories.

---

## 5. Resume from DESIGN
> "Resume ST-12 from DESIGN."

- The conductor reads the latest checkpoint for ST-12 and re-resolves the workspace (the planning
  repo HEAD moved).
- Preflight DESIGN: `ready-story` SATISFIED. However, `test-design` from an earlier attempt is
  **BLOCK** (stale): ST-12's AC changed after READY, so the AC hash no longer matches.
- qa-derive writes a **new** test design for the current AC. The old one is never edited.
- **Stop:** the run continues to the requested end, or to the end stored in the checkpoint.

---

## 6. LOW bug fix with an inline story
> "Fix the typo in the refund confirmation email."

- **Range:** IMPLEMENT → REVIEW.
- **Tier:** path-based lookup on `templates/email/refund.txt` gives LOW, and the type is `BUG_FIX`.
- **Preflight:** `ready-story` BACKFILL with `mode: INLINE_STORY`.
  - The PR body carries the story: objective, one AC, and one negative AC.
  - The readiness gate still checks it.
  - No separate plan file is needed.
- `conventions-catalog` is SATISFIED.
- **Run:** IMPLEMENT → TEST (red/green proof for the fix) → REVIEW.
- **Stop:** OBSERVED_STAGE (merge).

---

## 7. Add feature X to our existing service (conventions followed)
> "Add CSV export of refunds to `payments-svc`."

- **Range:** DESIGN → REVIEW for a new story. If no story exists, the run starts at PLAN.
- **Preflight:** `conventions-catalog` is BACKFILL because the catalog is stale: `package.json`
  is newer than it. The conductor re-runs
  `convention_scan.py --repo payments-svc --target src/refunds/`.
- **The catalog says:**
  - `web_framework: fastify`, `validation: zod`, `logging: pino`;
  - layers `routes → services → repositories`;
  - golden files `src/refunds/routes/list.ts` and `src/refunds/services/refund-query.ts`;
  - `notes: no_arch_conformance`.
- **DESIGN:** the architecture delta is "none". The feature fits the existing boundaries, so no ADR
  is needed. The test design is frozen.
- **IMPLEMENT** follows the declared and observed standards:
  - a new route in `routes/`, a service in `services/`, and a repository query;
  - zod schemas and pino logging, exactly as in the golden files.
- **One deviation:**
  - Problem: streaming CSV needs a library the repo doesn't have.
  - Decision: a DECISION plus ADR-14 "add fast-csv". architect REVIEWED; `human:tech-lead`
    APPROVAL is required at any tier (§4.15).
  - Enforcement: CODEOWNERS routes `package.json` to the tech lead, and `dependency-decision-check`
    links the manifest diff to ADR-14.
- **Existing problem:** an existing pattern (unbounded queries in `refund-query.ts`) is **reported**
  as a RISK plus a proposed TECHNICAL_STORY. It is not fixed in this change.
- **Run:** TEST → REVIEW. The code-reviewer checks conformance against `conventions.json` and the golden files.
- **Stop:** OBSERVED_STAGE.
