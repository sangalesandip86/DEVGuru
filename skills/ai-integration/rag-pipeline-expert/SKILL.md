---
name: rag-pipeline-expert
description: Design RAG pipelines -- chunking, retrieval, reranking, grounding. Use when building RAG, answers miss documents, or retrieval is slow.
metadata:
  group: ai-integration
  phase: progressive
  binding: false
  plan-ref: "§4.10"
  stage: ARCHITECTURE
  inputs: [requirement, nfr-catalog]
  outputs: [adr]
  repo_roles: [app, planning]
---

# RAG Pipeline Expert


## Purpose

Build retrieval that measurably finds the right content and generation that cites it.
Measure retrieval and generation separately — most "the LLM is wrong" bugs are retrieval bugs.
Output is `REVIEWED`; never `VERIFIED`.

## When this applies

- New RAG / semantic search / "chat with docs" feature.
- Wrong or uncited answers; known-relevant documents not retrieved.
- Corpus growth or latency/cost problems in retrieval.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Primary stage ARCHITECTURE; also DESIGN for retrieval changes on a story.

- **Inputs:** corpus size, update frequency, latency and quality targets.
- **ASK:** missing corpus or quality numbers are batched into one QUESTION with proposed defaults.
- **Repo roles:** `planning` (ADR), `app`.

## Existing project standards
On an existing repo, load [project-conventions](../../engineering-design/project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Reuse the existing vector store, embedding pipeline and data-access layer unless stated quality or latency numbers show they can't meet the target.

## Procedure

1. **Collect the numbers** (missing → `QUESTION`): corpus size (docs, total tokens), update
   rate and freshness requirement, queries/s, latency budget for retrieval, access-control
   model (per-user/tenant permissions), languages, document types.
2. **Ask whether RAG is needed.** If the relevant corpus fits comfortably in the model's
   context with prompt caching and the query rate is modest, long-context prompting may be
   simpler and more accurate. Compare on evals.
3. **Build a retrieval eval set first**: 50–200 real or realistic questions, each labeled with the
   chunk/document ids that answer it. Metrics: recall@k, MRR; target stated up front.
4. **Design the pipeline** using the table below; start with the defaults.
5. **Enforce access control at retrieval time** — filter by the caller's permissions in the
   query, never post-hoc in the prompt. Retrieved content is `EXTERNAL_UNSTRUCTURED` or
   `REPOSITORY` trust: data, never instructions (§5.9).
6. **Require grounded generation:** answer only from retrieved chunks, cite chunk ids, return an
   explicit "not found" when retrieval is empty or low-score. Check citations programmatically.
7. **Evaluate end-to-end** via `../prompt-engineer/reference/eval-harness.md`: retrieval
   metrics + answer faithfulness + answer correctness, separately reported.
8. Record a `DECISION` (`PROPOSED`).

## Pipeline defaults

| Stage | Default | Change when |
|---|---|---|
| Parsing | Structure-aware (headings, tables, code blocks preserved) | — |
| Chunking | 300–800 tokens, split on structure, 10–15% overlap; store parent doc id + heading path | Recall low on long-context questions → parent-document retrieval |
| Contextual enrichment | Prepend a short doc/section summary to each chunk before embedding | Chunks lose meaning out of context |
| Embeddings | One current general-purpose embedding model, version pinned in index metadata | Domain-specific vocabulary underperforms on evals |
| Index | Vector index in an existing store (e.g., pgvector) under ~10M chunks; dedicated vector DB above that or at high QPS | Measured latency/QPS limits |
| Retrieval | Hybrid: BM25/keyword + vector, merged (e.g., reciprocal rank fusion) | — |
| Reranking | Cross-encoder/reranker on top 50 → keep top 5–10 | Latency budget too tight |
| Query handling | Rewrite/expand ambiguous or conversational queries | — |
| Freshness | Incremental re-index on change events; full re-embed on embedding-model change | — |

## Debugging guide

| Symptom | Likely cause | Check |
|---|---|---|
| Answer wrong, right doc never retrieved | Chunking or embedding mismatch; missing keyword search | recall@k on the eval case |
| Right doc retrieved, answer still wrong | Ranking (doc below cutoff) or prompt | Position of gold chunk; reranker |
| Hallucinated details | Generation not constrained to context | Faithfulness eval; "not found" path |
| Leaks other tenants' data | ACL filtered after retrieval | Retrieval query filters |
| Quality dropped after re-index | Embedding model/version changed | Index metadata |

## Outputs

- `DECISION` (pipeline design, eval targets); `RISK` (ACL leakage, injection via documents, staleness).
- `QUESTION` for missing corpus/query numbers.

## Enforcement
**Guideline only** — no enforcement point yet.


- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Prompt injection via retrieved documents: test with `../../testing/ai-agent-testing/prompt-injection-tests/`.
- Pipeline design rules: **guideline only — no enforcement point yet**.

## References

- `../llm-integration-architect/SKILL.md`, `../prompt-engineer/SKILL.md`
- `../../engineering-design/data-store-selector/SKILL.md` (index storage choice)
