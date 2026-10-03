---
name: llm-integration-architect
description: Designs how an application integrates an LLM — model selection and tiering, API patterns (streaming, tool use, structured output, batching, caching), cost and latency budgets, failure handling, and safety boundaries — grounded in stated volume and latency numbers. Use when adding or changing an LLM-backed feature or agent.
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

# LLM Integration Architect

<!-- reconstructed: v2 source not provided; review -->

## Purpose

Produce an integration design that meets quality, latency, and cost targets with explicit
failure handling and trust boundaries. Output is `REVIEWED`; never `VERIFIED`.

## When this applies

- New LLM-backed feature, agent, or pipeline in product code.
- Changing models, providers, or call patterns for an existing feature.
- Cost or latency of an LLM feature exceeds budget.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Primary stage ARCHITECTURE; also DESIGN for story-level LLM features.

- **Inputs:** use-case requirements, latency/cost/quality NFRs, data-classification constraints.
- **ASK:** missing volume, latency or cost targets are batched into one QUESTION with proposed defaults.
- **Repo roles:** `planning` (ADR), `app` (existing integrations).

## Existing project standards
On an existing repo, load [project-conventions](../../engineering-design/project-conventions/SKILL.md) output (`.adlc/catalog/conventions.json`) and the project's declared standards (ADRs, AGENTS.md/CONTRIBUTING, lint/format/type and architecture-conformance configs) before recommending anything. Precedence: platform rules > declared project standards > observed conventions > this skill's generic guidance (plan §4.15).

- Recommending a different library, data store, broker, pattern or layer than the project already uses is a **deviation**: record a DECISION with a short ADR and get architect REVIEWED; a new dependency or changed architectural boundary also needs `human:tech-lead` APPROVAL.
- A problematic existing pattern is recorded as a RISK plus a proposed REFACTOR story — never fixed in passing inside unrelated work.
- Reuse the project's existing LLM client, provider abstraction and config approach; a new SDK or provider is a deviation.

## Procedure

1. **Collect the numbers** (each with a source; missing → `QUESTION`):

   | Input | Example |
   |---|---|
   | Requests/day and peak requests/s | 200k/day, peak 15/s |
   | Input / output tokens per request (p50, p95) | 3k / 400 |
   | Latency target (time-to-first-token, total) | TTFT < 1.5 s |
   | Quality bar and how it's measured | ≥ 90% on eval set X |
   | Monthly cost ceiling | $N |
   | Data sensitivity / residency | PII present; EU only |

2. **Choose model tier per step**, not per feature. Use the cheapest tier that passes the eval
   bar for that step (see table). Keep the model id in configuration, not code.
3. **Choose call patterns** from the pattern table below.
4. **Design the trust boundary.** Apply §5.9 Rule of Two to any agentic flow: a session that
   reads untrusted input must not also hold secrets *and* be able to mutate external state.
   Tool permissions are allow-listed per step; model output that drives actions is validated
   against a schema before execution.
5. **Design failure handling:** timeouts, retries with backoff on rate-limit/overload errors,
   fallback model or degraded response, and a circuit breaker. Never silently drop a failed call.
6. **Estimate cost** = requests × (input tokens × input price + output tokens × output price),
   adjusted for cache hit rate and batch discounts. Show the arithmetic; use current published pricing as the source.
7. **Plan evaluation** via `../prompt-engineer/reference/eval-harness.md` — the integration is
   not ready until the eval bar is met on the chosen model.
8. Record a `DECISION` (`PROPOSED`) with the design and cost estimate.

## Model tiering (defaults — re-check current model list before deciding)

| Tier | Default model | Use for |
|---|---|---|
| Strong | `claude-opus-5-5` | Complex reasoning, agentic coding, planning, high-stakes judgment |
| Balanced | `claude-sonnet-5-5` | Most production features; strong quality at lower cost/latency |
| Fast/cheap | `claude-haiku-4-5-20251001` | Classification, routing, extraction, high-volume simple steps, sub-agents |

Keep vendor-neutral seams: a thin provider interface (`complete`, `stream`, `tool_call`,
`embed`), model ids and prices in config, and eval sets that can run against any provider.
Do not leak provider-specific response objects past that interface.

## Call patterns

| Pattern | Use when |
|---|---|
| Streaming | User-facing text; improves perceived latency (TTFT) |
| Structured output / tool schemas | Output is consumed by code |
| Tool use / agent loop | Model must fetch data or act; bound the loop (max iterations, per §4.1 failure catalog) |
| Prompt caching | Large stable prefix (system prompt, documents) reused across calls — put stable content first |
| Batch API | Offline/bulk work with no latency requirement — significantly cheaper |
| Retrieval (RAG) | Knowledge too large or volatile for the prompt — see `../rag-pipeline-expert/SKILL.md` |
| Router / cascade | Cheap model first, escalate to stronger model on low confidence or failed validation |

## Outputs

- `DECISION` (architecture, model per step, patterns, budgets).
- `RISK` entries: injection exposure, cost overrun, provider outage, data leakage.
- `QUESTION` entries for missing numbers or quality bar.

## Enforcement

- Evidence rules: `../../grounding/evidence-gate/SKILL.md`.
- Rule of Two for agentic features is enforced in this platform by session scoping (§5.6 row 2);
  in *product* code it is a design requirement — **guideline only — no enforcement point yet**.
- AI-feature security tests: `../../testing/ai-agent-testing/`.

## References

- `../prompt-engineer/SKILL.md`, `../rag-pipeline-expert/SKILL.md`
- `../../skill-routing/token-budget-optimizer/reference/model-tiering.md` (platform's own model tiering)
