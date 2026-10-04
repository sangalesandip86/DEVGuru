# AI Inventory & Impact Assessment

## Purpose

This document inventories every AI agent role in the platform, its tools, data access, and
trust boundaries. It satisfies NIST AI 600-1 MAP-1 (identify AI capabilities and limitations),
ISO/IEC 42001 6.1.4 (AI risk assessment), and EU AI Act Art. 4 (AI literacy — personnel
understand the AI systems they deploy). It is the single page a compliance reviewer needs to
answer: "what AI runs here, what can it do, and what stops it from doing more?"

> Last updated: 2026-10-04.

## AI Agent Roles

| Role | Purpose | LLM Tier | Operation Classes | Data Classes Accessed | MCP Tools | Rule-of-Two Legs (max 2 of 3) |
|---|---|---|---|---|---|---|
| product-owner | Intent, value, priority of requirements; marks READY_FOR_APPROVAL | strong | READ, WORKSPACE_WRITE, REPO_WRITE | Requirements, stories, acceptance results | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Untrusted input (user docs) — 1/3 |
| product-planner | Decomposes requirements into plans/epics/stories with typed ACs | strong | READ, WORKSPACE_WRITE, REPO_WRITE | Requirements (text), stories (structured), public docs | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Untrusted input (user docs) — 1/3 |
| architect | Holistic design decisions grounded in stated numbers; sets REVIEWED on design | strong | READ, WORKSPACE_WRITE, REPO_WRITE | Architecture docs, NFRs, service maps, conventions, all source (read) | record_evidence, query_evidence, record_correction, get_change_set, record_handoff, record_dependency, check_compatibility, detect_drift | Untrusted input (requirements) — 1/3 |
| developer | Implements READY stories under approved plan; writes unit tests; feasibility JUDGMENT | default | READ, WORKSPACE_WRITE, REPO_WRITE | Source code, config, dependencies, test fixtures, plans | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Untrusted input (issue text) + repo write — 1/3 |
| qa-derive | Test oracle: implementation-blind, derives test design from ACs and contracts only | default | READ, WORKSPACE_WRITE, REPO_WRITE | ACs, test designs, contracts, step patterns (no source code) | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | None (code-blind by design) — 0/3 |
| qa-diagnose | Diagnoses test failures by reading implementation, logs, traces; sets REVIEWED on diagnoses | default | READ, WORKSPACE_WRITE, REPO_WRITE | All source (read), test paths (write), test results | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Untrusted input (test output) — 1/3 |
| test-engineer | Binds frozen test design to real repo; discovers stack, picks mode, writes test code | default | READ, WORKSPACE_WRITE, REPO_WRITE | Test code, fixtures, test-design schemas, stack facts | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Untrusted input (fixtures) — 1/3 |
| security-reviewer | Independent security pass; REVIEWED with ACCEPT/REJECT; REJECT blocks until human lifts | strong | READ | All source (read-only), dependencies, threat models | record_evidence, query_evidence, record_correction, get_change_set, record_handoff, query_incidents | Read-only — 0/3 |
| code-reviewer | Correctness/maintainability/conformance review of diffs; read-only | default | READ | Source code, diffs, conventions, handoff payloads | record_evidence, query_evidence, record_correction, get_change_set, record_handoff | Read-only — 0/3 |

**Notes:**
- "strong" model tier = reasoning-capable model (e.g. Opus-class); "default" = standard (e.g. Sonnet-class). Exact model IDs are deployment-time config.
- security-reviewer and code-reviewer for HIGH/CRITICAL require `model_family_constraint: different-from-implementer`.
- No agent role has EXTERNAL_MUTATION or DEPLOY operation classes.
- qa-derive has read-deny on `src/`, `lib/`, `app/`, `pkg/`, `internal/`, `cmd/`, `services/` and Bash deny — enforced via managed settings.

## Trust Boundaries — Three-Way Authority Split

| Authority | Set by | Enforcement | Example |
|---|---|---|---|
| **REVIEWED** | Agent (scoped to its role's domain) | MCP `record_evidence` validates caller identity and classification | architect sets REVIEWED on design; code-reviewer on code quality |
| **VERIFIED** | Server, from machine evidence only | `record_gate` requires SYSTEM identity; CI produces forge events | CI test pass → VERIFIED; merge event → forge event |
| **APPROVED** | Human only | `update_status` rejects agent callers for APPROVED/INTEGRATED/RELEASED; `ingest_forge_event` requires SYSTEM | human:tech-lead approves PLAN_APPROVED; human:release-manager approves RELEASED |

No agent can set: APPROVED, VERIFIED, INTEGRATED, RELEASED, PLAN_APPROVED, READY, DONE, ACCEPTED, or tracker state.

## Enforcement Controls

All enforcement artifacts are tracked in [`enforcement-map.md`](../enforcement-map.md) with three categories:

- **Enforced** (25 rules): artifact exists + test exercises the block. Includes ledger append-only integrity, agent identity authenticity, control-file write denial, per-role tool denies, checkpoint validation, and impact-plan checks.
- **Detects** (11 rules): artifact reports or flags the condition but nothing blocks on it yet. Includes dependency decisions, convention scan, milestone gates, skill routing, and DORA metrics.
- **Guideline** (16 rules): prose instruction only; no enforcement artifact. See residual risks below.

## Risk Assessment

### Residual risks (from Guideline items lacking enforcement)

| Risk | Current mitigation | Target enforcement |
|---|---|---|
| Developer holds Bash + reads untrusted issues + writes to repo | Sandbox mode with filesystem allow-list scoped to Change Set; no secrets in agent sessions | Vendor sandbox with session-level scoping (Rule of Two runtime) |
| qa-derive code-blindness unenforceable on Copilot/Bash | Enforced on Claude Code via managed-settings read-deny; Copilot has no path-deny primitive | Route blind roles to Claude Code or sandbox |
| 3-attempt iteration cap is a guideline | Orchestrator follows it; no runtime enforcement | Map to subagent `maxTurns` in agent frontmatter |
| Red/green check, flake gate, mutation scoring are stubs | DoD gates exist but these specific checks are not yet implemented | `red_green_check.py`, `flake_gate.py`, mutation adapters |
| No session-level Rule of Two runtime | Designed; developer role has Bash + reads untrusted issues | Vendor sandbox is the target primitive |
| Tracker projection (agents never write the tracker) | CI projects; `tracker_projection.py` does not exist | Script + CI job |
| Reviewer model-family diversity for HIGH/CRITICAL | Specified in role.yaml; no server-side check | Server check on `record_handoff` |

### Highest-risk interaction

The **developer** role has Bash + reads untrusted issue text + writes to repo. This is 1 of 3
Rule-of-Two legs (no secrets, no external mutation). Mitigated by: sandbox filesystem allow-list
scoped to Change Set paths, control-file deny rules, and human-gated PRs (never self-merges).

## Data Flow

```
User docs/requirements → product-planner → stories (plans/)
                                         ↓
stories → architect → architecture docs → developer → code (PR)
                                         ↓
stories (ACs only) → qa-derive → test designs → test-engineer → test code
                                         ↓
code + tests → CI gates → Evidence Ledger ← forge events (merge, deploy, review)
                                         ↓
Evidence Ledger → readiness/completion gates → derived status (READY/DONE)
```

## Review Cadence

- **Quarterly:** full review of this inventory against current role specs and enforcement map.
- **On role change:** any addition, removal, or modification of a role in `skills/roles/*/role.yaml` triggers an update to this document.
- **On tool surface change:** new MCP tools, new managed-settings deny rules, or new enforcement artifacts trigger an update.
- **On framework update:** changes to NIST AI 600-1, ISO 42001, or EU AI Act requirements trigger a compliance review.
