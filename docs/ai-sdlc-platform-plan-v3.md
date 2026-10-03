# AI SDLC Platform — Consolidated Build Plan v3

> How to use this document: Section 3 is the full folder tree — use it as your scaffold. Section 4 gives each skill's spec in the same order — use it to write each `SKILL.md` accurately. Section 5 is shared logic every skill should reference rather than reinvent. Section 6 documents MCP server design. Section 7 is pilot rollout and measurement. Section 8 tells you which native mechanism in Claude Code / GitHub Copilot each piece maps onto. Section 9 is the order to actually build it in.
>
> **v3 changes (from an independently-verified review pass on v2):** three-way REVIEWED/VERIFIED/APPROVED authority split (v2's VERIFIED was being set by agent judgment, not just machine evidence); authenticated identity for the Evidence Ledger (agent_role and trust_level are now server-derived, never caller-supplied); hash-chained, append-only ledger with a real correction mechanism; forge events (PR merge, CI deploy, CODEOWNERS review) as the source of truth for INTEGRATED/RELEASED/APPROVED instead of agent-settable fields; single-repo Change Sets now default to issue+PR on the forge, deferring the custom Change Set state machine to real multi-repo/parallel work; control-files trust category with mandatory CRITICAL-tier human approval on any write to platform configuration; fixed the Phase-1/Phase-3 circularity in mandatory risk-tier bindings; QA split into qa-derive and qa-diagnose with enforced (not just instructed) tool scoping; reviewer model-family diversity for HIGH/CRITICAL; Task/Checkpoint schema embedded in the Change Set; snapshot staleness path-classes; domain-scoped conflict resolution replacing a flat authority ranking; OWASP Top 10 for Agentic Applications mapping for AI-agent testing; corrected AGENTS.md precedence behavior; a rule → skill → enforcement-point mapping table; pilot baseline metrics and autonomy gating.

---

## Table of Contents

1. [Overview & Core Principles](#1-overview--core-principles)
2. [Build Phases](#2-build-phases)
3. [Complete Skill Catalog](#3-complete-skill-catalog)
4. [Skill Specifications](#4-skill-specifications)
5. [Cross-Cutting Design Rules](#5-cross-cutting-design-rules)
6. [MCP Server Design](#6-mcp-server-design)
7. [Pilot & Measurement](#7-pilot--measurement)
8. [Tool Compatibility — Claude Code / GitHub Copilot](#8-tool-compatibility--claude-code--github-copilot)
9. [Build Sequence](#9-build-sequence)

---

## 1. Overview & Core Principles

**What this is:** an AI-agent platform for the software development lifecycle (ADLC), built as a catalog of skills, subagent roles, and enforcement hooks, meant to run inside Claude Code and GitHub Copilot-class coding assistants. It treats the **Change Set** — not the repository — as the unit of work, and is built around evidence-grounded reasoning rather than confident-sounding guesses.

**Non-negotiable principles:**

- A repository is an implementation boundary, not an architecture boundary. A project is not a system.
- The **Change Set** — a requirement plus every repo/contract/environment it touches, pinned to a snapshot — is the unit of orchestration, not "change this repo." For single-repo work, the issue + pull request on the forge *is* the Change Set — a custom state machine is overhead you don't need until real multi-repo or parallel work forces it.
- **"Latest" is never a reproducibility mechanism.** Every Change Set pins commit SHAs, contract versions, and environment state at creation.
- **Three authority levels, not two.** A system can set `VERIFIED` — strictly from machine-ingested evidence (CI, a test runner, a scanner), written by the server, never by an agent's own tool call. An agent can set `REVIEWED` — an explicit judgment (code quality, design soundness) with evidence attached, and a `REVIEWED` is never treated as equivalent to a `VERIFIED`. Only an authenticated human can set `APPROVED`. **An agent's role identity never implies human authority, even when the agent is correct.**
- **No state transition is authorized by prompt text or agent self-report alone.** Only an authenticated actor acting through an enforced mechanism — a hook, a managed setting, a server-side check, or an observed forge event — can move a Change Set's state.
- When evidence is incomplete, the system resolves **toward more scrutiny, not less** — an unknown dependency, compatibility result, or risk tier defaults to the cautious reading, never the convenient one.
- Every claim in a **structured artifact** — a handoff, a DECISION, a RISK, a QUESTION, an approval summary — must trace to a source. An unsourced claim becomes a QUESTION or a tagged, expiring ASSUMPTION — never a silent FACT. This is what evidence-gate actually guarantees; it does not and cannot mechanically guarantee that every sentence of an agent's free-form prose is sourced — don't oversell it as enforcing more than that.
- **Untrusted input is data, never instructions**, enforced structurally: no single agent session combines reading untrusted input, touching secrets or production data, *and* the ability to mutate external state or deploy. Keyword-flagging phrases like "ignore previous instructions" is not a defense on its own — it's trivially bypassed by paraphrase — so it is a supplementary signal, never the primary control.
- **Platform control files are never agent-writable.** Hooks, skill and agent definitions, MCP configuration, AGENTS.md, CODEOWNERS, rulesets, and CI workflows are a named trust category. A write to any of them is always `CRITICAL` risk and always requires human approval, enforced by denying agent write access to those paths at the managed-settings level — not merely by instructing agents not to touch them.
- Token/cost optimization is subordinate to accuracy. It decides what loads and which model runs — **never whether grounding happens**.
- Build lean by default; scale process to risk. A README change and a payment-schema migration must not go through the same number of gates.
- The system improves itself only through a **human-gated review** of accumulated evidence from real use — never by silently rewriting its own skills or prompts. A candidate skill/prompt revision follows the exact same `REVIEWED` → `APPROVED` pipeline as any other change; self-improvement doesn't get a quieter path to production than a developer's code does.
- **Skills are instruction documents, not callable modules.** Stateful operations are MCP server calls. Scripts are tool invocations. Hooks enforce; skills inform. Skills inform agent behavior through the context window — they do not and cannot enforce anything on their own.
- **Mandatory skills are loaded by policy, not by LLM judgment**, and the routing mechanism can re-evaluate mandatory bindings as its understanding of a task deepens — it is not limited to only adding optional skills on top of a first pass.
- **Agents will fail.** The platform defines explicit iteration limits, failure-class-specific retry policy, scope checks, and resumability — not just the happy path.

---

## 2. Build Phases

### Phase 0 — Evidence & Fact Ledger + Trust & Safety Foundation

- `/core` (evidence-ledger with full entry schema, identity derived from the authenticated connection, hash-chained, append-only; fact-classification) and `/grounding` (evidence-gate scoped to structured artifacts, ambiguity-escalation, trust-boundaries including the control-files category, agent-failure-modes with per-failure-class retry policy, human-review-format) — binding from day one, single repo, no multi-repo orchestration yet.
- `/enforcement` — hooks that write `FACT`-classified ledger entries directly from command output and file reads (zero model tokens, cannot be skipped because they run regardless of what the model decides); managed-settings templates that deny agent write access to control-file paths; CI checks that verify those settings are actually in place.
- **A lightweight, path-based risk-tier lookup** ships in Phase 0 — a short table mapping path patterns (payment/, auth/, */migrations/, etc.) directly to a tier. This exists specifically so that nothing in Phase 1 is ever left unable to compute a tier at all before the full risk-tiering MCP capability exists (see §2's Degraded Mode note below — this closes a real circularity in the original mandatory-binding design).
- `/governance/default-permissions` — basic role-to-tool permission boundaries, enforced via each platform's native scoping. No tool exposed to an agent-authenticated caller can ever set status to `APPROVED`, `INTEGRATED`, or `RELEASED` — those are server-internal transitions triggered by forge events or an authenticated human action, never a callable agent tool.
- **Evidence Ledger MCP server** (Server 1) — the shared backbone for provenance, `/self-improvement`, and later engines. Build it here, not later, with authentication from the start.
- **Don't build a custom eval harness.** Skill-creator's existing loop (draft → test prompts → grade → analyze → iterate, backed by `evals.json` / `grading.json`) is the harness. Everything this phase produces should be gradeable by it.

### Phase 1 — Scoped Skills + Context Router + Roles

- `/skill-routing` in full — two-phase routing where **Phase 2 of routing can re-run the mandatory-binding check against its own deeper analysis**, not just add advisory skills on top of Phase 1's keyword match. Any mandatory trigger Phase 2 catches that Phase 1 missed logs to self-improvement as a near-miss — that's the signal the keyword list needs expanding.
- **Single-repo Change Sets default to forge-native execution**: the issue + PR pairing on GitHub *is* the Change Set. `INTEGRATED` = an observed merge on the target branch. `RELEASED` = an observed deployment record plus an environment approval. Human `APPROVED` = an authenticated CODEOWNERS review or environment approval, ingested by the server. None of these are states an agent sets — they're facts the server observes. This keeps Phase 1 genuinely lightweight: the Change Management MCP server isn't needed until Phase 2's multi-repo/parallel case.
- First `/roles`: developer, **qa-derive** and **qa-diagnose** (QA's independent-derivation and diagnostic passes are two separately-scoped roles, not one role instructed to behave differently in each pass — qa-derive's tool permissions technically deny implementation file paths; qa-diagnose has full read access), code-reviewer.
- `/roles/reference/handoff-schema.md` and `/roles/reference/conflict-resolution.md` (domain-scoped rejection, not a flat authority ranking) — so handoffs are typed and traceable from day one, and `artifact_ref` values point at `repo@sha:path` plus a content hash, never a bare mutable filename.
- `/self-improvement` comes online here. Positive signals only count toward pattern detection when verification was strong enough to mean something (changed-code coverage, acceptance criteria actually exercised) — a clean run in a weakly-tested repo is tagged `unverified-positive` and excluded. Production feedback writes new correcting entries that reference the original — it never retags a past entry in place. Any candidate skill/prompt revision runs through the same `REVIEWED` (passes the eval suite) → `APPROVED` (human) pipeline as everything else.
- `/testing/security-testing` and `/testing/ai-agent-testing` — the latter mapped onto the OWASP Top 10 for Agentic Applications (ASI01–ASI10), not an ad hoc list.
- For HIGH/CRITICAL tiers, at least one reviewer is on a different model family from the implementing agent, or is a deterministic tool — cheap to do since the platform already spans two tools.

### Phase 2 — Multi-Repo Change Set + Lightweight Dependency Discovery

- Now explicitly scoped to the case Phase 1's forge-native default doesn't cover: multiple repositories, or genuinely parallel work within one Change Set.
- `/change-management` in full: change-set (with lifecycle states, `tasks[]` embedded with checkpointing, parent/dependencies, completion criteria, resumability), snapshot (with staleness policy including always-overlap path classes), dependency-discovery (via static analysis — grep/import/call-graph — not a declared-contract model yet), risk-tiering (now the full MCP-backed capability, with reason-code-gated escalation and downgrade tracking), parallel-execution-rules (one isolated worktree per concurrently-running task).
- **Change Management MCP server** (Server 2) — stateful Change Set tracking, built here because this is where it first becomes necessary, not before.
- Risk-tiering decides which gates apply from day one, so simple tasks stay fast while complex ones get scrutiny.

### Phase 3 — Contracts, Compatibility, Multi-Repo Verification

- `/contracts` (contract-registry with type and compatibility direction, compatibility-check — now checking against versions actually recorded as deployed, drift-detection) — built against the dependency patterns Phase 2 actually surfaced, not a speculative model.
- **Contract Registry MCP server** (Server 3), including `record_deployment` fed by CI.
- Remaining `/roles` (product-owner, architect, security-reviewer) and remaining `/governance` (permission-scoping with fine-grained matrices, policy-drift-check).

### Degraded Mode — so the phased build order doesn't deadlock itself

A mandatory binding can require a role or capability that hasn't been built yet in the current phase — e.g., an early task computes a HIGH tier (nominally requiring architect + security-reviewer, both Phase 3) while those roles don't exist until later. The fix: when a `REQUIRED` capability isn't yet built, the Change Set routes to a **named human** standing in for that role, and the routing is recorded as that role's handoff target, not treated as a block. Humans filling early gaps is also the lowest-friction path to actual adoption. This has to be designed in from the start — a fail-safe default that can't be satisfied during early phases will otherwise silently stall everything or get quietly bypassed, which is exactly the failure mode the fail-safe principle exists to prevent.

### Explicitly deferred until a real need appears

- Full Portfolio/Program/Enterprise hierarchy — add only once more than one team needs shared requirements across systems.
- Signed/trusted skill supply chain — premature without third-party or external skill sources.
- A dedicated Capability Broker — start with native per-role/per-subagent tool and MCP scoping (both platforms already support this); build a broker only if manual scoping stops working.
- Full SLSA-level signed provenance — premature without a build/release pipeline. Core provenance fields in the Evidence Ledger are sufficient.
- Multi-dimensional risk scoring (11 dimensions, weighted scores) — the 4-tier model with fail-safe defaults is sufficient until observability data reveals which dimensions matter.
- Model capability matrix for routing — model capabilities change with every release; the current cheap/fast vs strong model heuristic is the right abstraction until you control your own orchestration runtime.
- A full semantic dependency graph — the declared "always-overlap" path classes (§4.5) catch the shared-library and base-image cases almost for free; the full graph waits for real Phase 3 data.
- A custom ALLOW/DENY/ESCALATE policy engine — enforce by construction instead (one credential per role, only role-appropriate tools exposed, no tool that sets a privileged state) until that stops being sufficient.

---

## 3. Complete Skill Catalog

```
/skills
├── /grounding                          [binding, cross-cutting — Phase 0+]
│   ├── evidence-gate/
│   │   └── reference/
│   │       └── evidence-gate-scope.md
│   ├── ambiguity-escalation/
│   │   └── reference/
│   │       ├── ask-vs-assume-matrix.md
│   │       └── fail-safe-defaults.md
│   ├── trust-boundaries/
│   │   └── reference/
│   │       ├── trust-level-classification.md
│   │       └── control-files.md
│   ├── agent-failure-modes/
│   │   └── reference/
│   │       └── failure-catalog.md
│   └── human-review-format/
│       └── reference/
│           └── presentation-rules.md
│
├── /self-improvement                   [binding, cross-cutting — Phase 1+]
│   ├── failure-capture/
│   │   └── reference/
│   │       ├── trigger-signals.md
│   │       ├── incident-schema.md
│   │       └── production-feedback.md
│   └── improvement-review/
│       └── reference/
│           ├── pattern-threshold.md
│           ├── eval-case-conversion.md
│           └── human-approval-gate.md
│
├── /core                               [Phase 0]
│   ├── evidence-ledger/
│   │   └── reference/
│   │       ├── ledger-entry-schema.md
│   │       └── identity-and-auth.md
│   └── fact-classification/
│       └── reference/taxonomy.md
│
├── /enforcement                         [Phase 0 — NOT skills; actual enforcement artifacts]
│   ├── hooks/
│   │   ├── fact-writer-hooks/          # PostToolUse hooks writing FACT entries directly
│   │   └── control-file-guard/         # PreToolUse hook blocking agent writes to control-file paths
│   ├── managed-settings/
│   │   └── templates/
│   └── ci-checks/
│       └── control-file-policy-check/
│
├── /mcp-servers                         [Phase 0+]
│   └── reference/
│       └── mcp-server-design.md        # see §6
│
├── /skill-routing                      [Phase 1]
│   ├── skill-router/
│   │   └── reference/
│   │       ├── scope-matrix.md
│   │       └── two-phase-routing.md
│   ├── binding-vs-advisory/
│   │   └── reference/
│   │       └── policy-precedence.md
│   └── token-budget-optimizer/
│       └── reference/
│           ├── model-tiering.md
│           ├── context-budget.md
│           ├── cost-controls.md
│           ├── context-compaction.md
│           ├── caching-strategy.md
│           └── budget-escalation.md
│
├── /change-management                  [Phase 2]
│   ├── change-set/
│   │   └── reference/
│   │       ├── changeset-schema.md
│   │       ├── changeset-lifecycle.md
│   │       ├── completion-criteria.md
│   │       ├── resumability-rules.md
│   │       ├── tasks-and-checkpoints.md
│   │       └── approval-matrix.md
│   ├── dependency-discovery/
│   │   └── scripts/
│   │       ├── scan-imports.py
│   │       └── scan-api-calls.py
│   ├── snapshot/
│   │   └── reference/
│   │       └── staleness-policy.md
│   ├── risk-tiering/
│   │   └── reference/
│   │       ├── risk-matrix.md
│   │       └── escalation-reason-codes.md
│   └── parallel-execution/
│       └── reference/
│           └── parallel-execution-rules.md
│
├── /contracts                          [Phase 3]
│   ├── contract-registry/
│   │   └── reference/contract-schema.md
│   ├── compatibility-check/
│   │   └── scripts/check-can-i-deploy.py
│   └── drift-detection/
│
├── /roles                              [progressive — Phase 1 onward]
│   ├── product-owner/
│   ├── architect/
│   ├── developer/
│   ├── qa-derive/
│   ├── qa-diagnose/
│   ├── security-reviewer/
│   ├── code-reviewer/
│   └── reference/
│       ├── handoff-schema.md
│       ├── conflict-resolution.md
│       └── reviewer-diversity.md
│
├── /testing                            [progressive]
│   ├── /test-architecture
│   │   ├── test-strategy/
│   │   └── test-pyramid-advisor/
│   ├── /web-ui-automation
│   │   ├── playwright-expert/
│   │   │   └── reference/
│   │   │       ├── selectors-best-practices.md
│   │   │       └── flaky-test-patterns.md
│   │   ├── selenium-expert/
│   │   ├── visual-regression/
│   │   └── headless-vs-headed/
│   ├── /mobile-automation
│   │   ├── appium-expert/
│   │   ├── ios-xcuitest/
│   │   ├── android-espresso/
│   │   └── device-matrix/
│   ├── /api-contract-testing
│   │   ├── pact-consumer-driven/
│   │   ├── postman-newman/
│   │   └── schema-validation/
│   ├── /test-maintenance
│   │   ├── flaky-test-intelligence/
│   │   │   └── scripts/flaky-detector.py
│   │   ├── test-data-management/
│   │   └── self-healing-locators/
│   ├── /performance-testing
│   │   ├── load-testing-expert/
│   │   │   └── reference/
│   │   │       ├── k6-scripts.md
│   │   │       └── jmeter-scripts.md
│   │   ├── perf-baseline-tracker/
│   │   └── bottleneck-analysis/
│   ├── /security-testing
│   │   ├── sast-scanner/
│   │   ├── sca-dependency-audit/
│   │   ├── secret-scanning/
│   │   └── deployment-verification/
│   └── /ai-agent-testing                # mapped to OWASP Top 10 for Agentic Applications (ASI01–ASI10)
│       ├── prompt-injection-tests/       # ASI06/ASI08-adjacent
│       ├── tool-misuse-tests/            # ASI02
│       ├── agent-authorization-tests/    # ASI03
│       └── policy-bypass-tests/          # ASI01, ASI09
│
├── /engineering-design                 [progressive]
│   ├── code-design-reviewer/
│   │   └── reference/
│   │       ├── solid-principles.md
│   │       ├── anti-patterns.md
│   │       └── performance-checklist.md
│   ├── system-architect/
│   │   └── reference/
│   │       ├── decomposition-patterns.md
│   │       └── scaling-playbook.md
│   ├── data-store-selector/
│   │   └── reference/decision-matrix.md
│   ├── messaging-selector/
│   │   └── reference/decision-matrix.md
│   └── scale-readiness-reviewer/
│
├── /ai-integration                     [progressive]
│   ├── prompt-engineer/
│   │   └── reference/
│   │       ├── prompt-patterns.md
│   │       └── eval-harness.md
│   ├── llm-integration-architect/
│   └── rag-pipeline-expert/
│
└── /governance                         [Phase 0 core + Phase 3 full]
    ├── default-permissions/
    │   └── reference/
    │       ├── role-tool-permissions.md
    │       └── control-file-policy.md
    ├── autonomy-gating/
    │   └── reference/
    │       └── verification-strength.md
    ├── permission-scoping/
    └── policy-drift-check/
```

---

## 4. Skill Specifications

### 4.1 `/grounding` — binding, cross-cutting

**evidence-gate**
- Purpose: no claim in a structured artifact leaves any skill without a cited source (file:line, command output, doc URL, or a user statement).
- Behavior: an unsourced claim is automatically converted to a QUESTION or a tagged ASSUMPTION — it never passes through as a silent FACT.
- `reference/evidence-gate-scope.md`:
  - **Guarantees:** every claim in a handoff, DECISION, RISK, QUESTION, or approval summary traces to a source.
  - **Does not guarantee:** that every sentence of an agent's free-form reasoning is individually sourced; that the conclusion drawn from a source is correct; that the output addresses the real requirement. Those are caught by QA verification, code review, self-improvement, and human review respectively.

**ambiguity-escalation** — unchanged from v2; see §5.2 and §5.3.

**trust-boundaries**
- Purpose: classifies every input source by trust level and enforces that untrusted content is treated as data, never as agent instructions.
- `reference/trust-level-classification.md`: SYSTEM / ORGANIZATIONAL / REPOSITORY / EXTERNAL_STRUCTURED / EXTERNAL_UNSTRUCTURED (unchanged table from v2).
- `reference/control-files.md` **(new)**: defines the **control-files** category explicitly — hooks, agent/skill/MCP configuration, AGENTS.md, CLAUDE.md, CODEOWNERS, rulesets, CI workflow definitions. A write to any of these:
  - Is always `CRITICAL` risk tier, regardless of what else is in the Change Set.
  - Always requires human approval — never satisfied by `VERIFIED` alone.
  - Is denied to agents at the **managed-settings** level (org-controlled, not repo-editable), not merely discouraged by instruction. A project-local setting can be rewritten by anyone with repo write access, or by an injected agent with shell access — that is not a control, it's a suggestion.
  - Is logged via a `ConfigChange`-class hook regardless of outcome.
  - Enforcement, not scanning, is the point: this exists because a real, exploited vulnerability class (prompt injection inducing an agent to write a permissive setting into a repo-local config file, then trusting that file) has already been demonstrated against AI coding agents in production. Treat this as a day-one requirement, not a later hardening pass.
- Enforcement note: content from EXTERNAL_UNSTRUCTURED sources containing agent-instruction patterns ("ignore previous instructions," "override policy," "skip verification") is flagged as a supplementary signal — never the primary defense, since pattern matching is trivially bypassed by paraphrase. The primary defense is structural: see the Rule-of-Two constraint in §5.9.

**agent-failure-modes**
- Purpose: defines what happens when agents fail, because agents WILL fail.
- `reference/failure-catalog.md`: failure modes, handling, **and now a retry-policy class**:

| Failure Mode | Handling | Retry Policy |
|---|---|---|
| Agent loops (generate → review → regenerate endlessly) | Iteration cap per task (default: 3 attempts), then BLOCKED + evidence of what was tried | RETRY (counts toward the 3-attempt cap) |
| Agent produces structurally invalid output | Output validation gate — does the output match the expected shape for its handoff? | RETRY |
| Agent misunderstands the task / scope violation | Does the output stay within Change Set scope? If it touches files/APIs outside scope, flag before accepting | ESCALATE immediately — does **not** draw from the 3-attempt budget |
| Agent hits tool failure (command error, MCP timeout) | Retry with backoff for transient errors; BLOCKED for persistent errors; never silently skip the tool call | RETRY (transient) / STOP (persistent) |
| Agent exceeds context window mid-task | Detect context pressure, checkpoint progress to Evidence Ledger, decompose remaining work into sub-tasks | REPLAN |
| Agent session crashes | Evidence Ledger entries from partial run persist; agent reads prior entries before regenerating | RESUME |
| Permission denial (agent attempted an action outside its scope) | Logged, blocked at the tool-permission layer | ESCALATE immediately — never retried |
| Security-gate rejection (security-reviewer rejects) | Treated as a correct, working control, not a failure to route around | ESCALATE to human — never silently retried into exhaustion |

  A scope violation, a permission denial, and a security rejection are not retry-worthy transient failures — burning down the same 3-attempt counter used for a flaky tool timeout would either exhaust the budget on a legitimate block, or worse, create pressure to keep trying until something slips through.

**human-review-format** — unchanged from v2.

### 4.2 `/self-improvement` — binding, cross-cutting

**failure-capture**
- Purpose: watches every skill/agent's output; on a signal (negative, positive, or efficiency), writes a structured record.
- Triggers (`reference/trigger-signals.md`): unchanged from v2 (negative / positive / efficiency / production signal types).
- `reference/incident-schema.md`: FACT / INFERENCE / PROPOSAL structure, shaped to match skill-creator's `evals.json` / `grading.json`.
- `reference/production-feedback.md` **(revised)**: a production incident, rollback, or performance regression linked to a Change Set writes a **new ledger entry** with `outcome_status: CHALLENGED` and a reference to the original entry's `entry_id`. It never retags or mutates the original — that would violate the ledger's own append-only guarantee (§4.3). The new entry carries the INFERENCE tag for any hypothesized root cause, explicitly unconfirmed.
- **Positive-signal quality gate**: a positive signal only counts toward pattern detection when verification was strong enough to mean something — changed-code test coverage, acceptance criteria actually exercised. A clean first-pass in a weakly-tested repo is tagged `unverified-positive` and excluded from pattern detection; otherwise the self-improvement loop learns from the absence of scrutiny, not from genuine quality.

**improvement-review**
- Purpose: periodically turns accumulated signals into an actual skill/prompt improvement, gated by a human.
- `reference/pattern-threshold.md`, `reference/eval-case-conversion.md`: unchanged from v2.
- `reference/human-approval-gate.md` **(revised)**: a candidate revision that passes skill-creator's grader/analyzer/optimization loop is marked `REVIEWED` (automated evidence of improvement) — not `APPROVED`. A human reviews the evidence and sets `APPROVED` before it replaces the live skill. Self-improvement follows the identical authority split as every other change in the platform; it does not get a quieter path to production.
- Storage: another table in the same Evidence Ledger — not a separate logging system.

### 4.3 `/core`

**evidence-ledger**
- Purpose: records what every agent run read, decided, and assumed, for audit and for feeding `/self-improvement`.
- `reference/ledger-entry-schema.md`:

| Field | Description | Required |
|---|---|---|
| `entry_id` | Unique identifier for this entry | Yes |
| `run_id` | Identifier for the agent execution run | Yes |
| `change_set_id` | The Change Set this entry belongs to (null for platform-level operations) | No |
| `actor_type` | `HUMAN` / `AGENT` / `SYSTEM` — **new** | Yes |
| `actor_id` | The specific human, agent role, or system process — **new**, server-derived | Yes |
| `agent_role` | Which role produced this entry (developer, qa-derive, etc.), when `actor_type` is AGENT | Conditional |
| `model_id` | Which model was used | Yes for AGENT entries |
| `tool` | `claude-code` \| `copilot` — **new** | Yes |
| `classification` | FACT / INFERENCE / ASSUMPTION / PROPOSAL / QUESTION / DECISION / RISK | Yes |
| `trust_level` | SYSTEM / ORGANIZATIONAL / REPOSITORY / EXTERNAL_STRUCTURED / EXTERNAL_UNSTRUCTURED — server-derived from a `source_type` map, never caller-supplied | Yes |
| `content` | The actual claim, decision, or observation | Yes |
| `source` | Where this came from (file:line, command output, doc URL, user statement) | Yes for FACT |
| `input_references` | IDs of evidence entries this was derived from | Yes for INFERENCE |
| `output_references` | IDs of artifacts/files this produced | No |
| `decision_ids` | IDs of related DECISION entries | No |
| `lifecycle_state` | For DECISION/PROPOSAL entries: DRAFT / PROPOSED / REVIEWED / VERIFIED / APPROVED / REJECTED (`REVIEWED` added — see §5.5) | No |
| `snapshot_id` | Which snapshot this entry was made against — **new** | No |
| `parent_entry_id` | For a correcting entry, the `entry_id` it corrects — **new, required for the append-only correction mechanism to actually work** | No |
| `platform_release_sha` | One value covering the skill/role/policy version in effect — **new** | Yes |
| `timestamp` | ISO 8601 timestamp | Yes |
| `signal_source` | For self-improvement: AGENT / REVIEWER / HUMAN / PRODUCTION | No |

- Entries are **append-only** — no entry is ever deleted or modified. Corrections are new entries with `parent_entry_id` set, never an edit to the original.
- `reference/identity-and-auth.md` **(new)**:
  - `agent_role`, `actor_id`, and `trust_level` are **derived server-side from the authenticated connection** — never accepted as caller-supplied parameters. A caller claiming to be `qa-derive` must actually be authenticated as that role's credential; nothing is taken on self-report.
  - One credential per role. The MCP server's tool surface exposes only role-appropriate tools — there is no tool through which an agent-authenticated caller can write an `APPROVED`, `INTEGRATED`, or `RELEASED` status.
  - FACT-classified entries (command output, file reads) are written **by hooks directly** — zero model tokens, and they cannot be skipped because hooks run regardless of what the model decides. The model only ever writes INFERENCE, ASSUMPTION, DECISION, QUESTION, PROPOSAL, and RISK entries.
  - Entries are **hash-chained** — each entry includes a hash of the prior entry — so tampering is detectable even on a local file.
  - A per-workspace SQLite database is acceptable for a true single-user, single-workspace pilot only. Once more than one person, or any cloud-hosted agent session, is involved, move to a remote authenticated MCP service, reusing whatever OAuth2/mTLS/RBAC layer the rest of the platform's integrations already use rather than designing a new one.

**fact-classification** — unchanged from v2; see §5.1.

### 4.4 `/skill-routing`

**skill-router**
- `reference/scope-matrix.md`: unchanged mandatory/contextual split from v2.
- `reference/two-phase-routing.md` **(revised)**:
  - **Phase 1 — Coarse routing**: keyword/pattern matching against scope-matrix mandatory bindings on requirement text, repo names, and file paths. Cheap, fast, always includes binding skills, may over-include.
  - **Phase 2 — Refined routing**: runs after initial analysis (risk tier, dependency scan, etc.). Can ADD contextual/advisory skills **and can re-evaluate the mandatory-binding computation itself** against its own deeper understanding of the task — it is not limited to additive, advisory-only changes. If Phase 2 determines a mandatory trigger applies that Phase 1's keyword match missed (e.g., "update the fee calculation in `BillingAdjuster.java`" has no literal "payment" keyword but is clearly payment-domain code), it applies the mandatory binding retroactively for the rest of the task **and logs the miss to self-improvement as a near-miss** — repeated near-misses are the signal that the keyword list needs expanding, not a one-off tolerance.
  - Phase 2 can never *remove* a binding skill Phase 1 correctly included. If in doubt, over-include — removing is cheaper than missing.

**binding-vs-advisory** — unchanged from v2; see `reference/policy-precedence.md`.

**token-budget-optimizer**
- `reference/model-tiering.md`, `reference/context-compaction.md`, `reference/caching-strategy.md`, `reference/budget-escalation.md`: unchanged from v2.
- `reference/context-budget.md` and `reference/cost-controls.md`: the 60% context-decomposition threshold and the 20/40/30/10 per-role budget split are **default policy values**, not fixed constants — they're overridable and meant to be tuned from the cost-per-phase data the Evidence Ledger already records. A multi-factor "reasoning complexity" formula is explicitly out of scope until something measurable actually feeds it; the simple heuristic, tuned by real data, is the right level of sophistication for now.

### 4.5 `/change-management`

**change-set**
- `reference/changeset-schema.md`: id, system, initiative, requirements, repositories, contracts, environments, status, `parent_id`, `depends_on[]`, plus:
- `reference/tasks-and-checkpoints.md` **(new)**: `tasks[]` embedded directly in the Change Set record:

```yaml
tasks:
  - id: TASK-14
    depends_on: [TASK-12]
    owner_role: developer
    worktree: /workspaces/CS-881/task-14
    attempts: 1
    checkpoint:
      commit_sha: a1b2c3d
      ledger_cursor: ENTRY-9981
      snapshot_id: SNAP-220
```

  This closes the gap where v2's prose described tasks extensively (lifecycle, parallel-execution rules) without the schema actually having anywhere to represent one.

- `reference/changeset-lifecycle.md` **(revised)**:

```
DRAFT → SCOPED → PLANNED → PLAN_APPROVED → EXECUTING → VERIFYING → INTEGRATED → RELEASED

Side states:
  BLOCKED — a gate failed, a dependency is unmet, or escalation triggered
            (returns to the state the Change Set was in immediately before BLOCKED,
             once the blocking condition is resolved)
  FAILED — unrecoverable error after exhausting retry/replan options
  CANCELLED — abandoned by human decision

Reachable only from RELEASED:
  ROLLED_BACK — was RELEASED but reverted due to a production issue
```

  `PLAN_APPROVED` replaces v2's ambiguous `APPROVED` state name, which collided with the entry-level `APPROVED` lifecycle_state and with release approval. `ROLLED_BACK` is no longer listed as reachable from any active state — you cannot roll back something that was never released.
- `reference/completion-criteria.md` **(revised)**: a Change Set can move to `INTEGRATED` only when ALL of: (1) all required gates for its risk tier have passed; (2) no UNRESOLVED dependencies remain; (3) no unexpired ASSUMPTIONs with impact > LOW remain; **(4) no OPEN QUESTION tagged `blocking: true` remains** (QUESTIONs now carry OPEN / ANSWERED / EXPIRED state, and an open blocking question fails this gate the same way an unresolved dependency does); (5) all required roles have produced their handoff; (6) all repositories in the Change Set have passing verification.
- `reference/approval-matrix.md` **(new)** — resolves the one authoritative human-approval requirement per tier and transition, replacing three different implied rules that existed in v2:

| Tier | `PLANNED → PLAN_APPROVED` | `INTEGRATED → RELEASED` |
|---|---|---|
| LOW | None required — VERIFIED is sufficient | None required — forge merge + CI deploy is sufficient |
| MEDIUM | None required — VERIFIED + code-reviewer REVIEWED | `human:tech-lead` |
| HIGH | `human:tech-lead` | `human:security-lead` |
| CRITICAL | `human:security-lead` AND `human:product-owner` | `human:release-manager` |

  Human approvers are named by role with a `human:` prefix, disambiguating them from the identically-named `developer` **agent** role elsewhere in the catalog.
- `reference/resumability-rules.md`: unchanged from v2, with one scope correction — the "VERIFYING catches it" safety reasoning applies only to `REPO_WRITE`-class operations on a branch (see Operation Classes below). It does not apply once an `EXTERNAL_MUTATION` or `DEPLOY`-class operation has occurred — those are not undoable by a later verification step.

**dependency-discovery** — unchanged from v2.

**snapshot**
- `reference/staleness-policy.md` **(revised)**: in addition to the file-path overlap check from v2, a **declared list of path classes always counts as overlapping**, regardless of exact path match: lockfiles, dependency manifests, IaC files, migration files, schema files, CI config, feature-flag files. This catches the shared-library-bump and base-image-change cases that a literal path-overlap check misses, without needing a full semantic dependency graph.

**risk-tiering**
- `reference/risk-matrix.md`: unchanged.
- `reference/escalation-reason-codes.md` **(new)**: agent-expressed uncertainty escalates the tier by exactly one level (never more), and only for a closed, named list of reason codes — `UNRESOLVED_DEPENDENCY`, `UNKNOWN_BLAST_RADIUS`, `SENSITIVE_PATH`, `COMPATIBILITY_UNKNOWN` — not any agent's general sense of unease. Every human downgrade of an escalated tier is logged. A rising downgrade rate is an early warning that the escalation logic is miscalibrated and that developers will start routing around the platform rather than working with it.

**parallel-execution**
- `reference/parallel-execution-rules.md` **(revised)**: each concurrently-running task gets its **own isolated git worktree**, not just a branch — two tasks on different branches cannot safely share one checked-out working tree. Conflict detection, partial-completion handling, and merge ordering are unchanged from v2.
- **Operation classes** (new, cutting across this whole section): `READ`, `WORKSPACE_WRITE`, `REPO_WRITE` are available to agents. `EXTERNAL_MUTATION` and `DEPLOY` are never available to agents directly — only to CI and the server, triggered by an observed, authorized event. This is what correctly scopes the resumability claim above: "it's safe because it's on a branch and VERIFYING will catch it" is true for `REPO_WRITE`; it is not true the moment an operation crosses into `EXTERNAL_MUTATION` or `DEPLOY`.

### 4.6 `/contracts`

**contract-registry** — unchanged from v2.

**compatibility-check**
- `scripts/check-can-i-deploy.py`: validates compatibility against **actually recorded deployed versions** (via Server 3's `record_deployment`, fed by CI — see §6), not "latest against latest" and not a guess.
- Compatibility direction (old producer → new consumer, new producer → old consumer) and the INCOMPATIBLE-by-default rule: unchanged from v2.

**drift-detection** — unchanged from v2.

### 4.7 `/roles`

Each role is a subagent definition; each must reference `/grounding/evidence-gate` rather than redefine accuracy rules itself.

- **product-owner** — turns ambiguous requests into scoped requirements; raises QUESTIONs for genuine ambiguity. Marks a requirement `READY_FOR_APPROVAL` — it does not itself `APPROVE` requirements; that word is reserved for an authenticated human throughout the platform (see §5.5).
- **architect** — holistic design decisions; must ground recommendations in stated numbers (scale, QPS, data volume), not generic pattern-matching. Can set `REVIEWED` on a design judgment — never `VERIFIED`.
- **developer** — implementation; works from an approved plan and the current Change Set snapshot.
- **qa-derive** — Pass 1 of verification: derives test cases from the requirement text and acceptance criteria. Implementation file paths are **technically denied** at the tool-permission level during this pass, not merely avoided by instruction — this is what makes the independence claim enforceable rather than aspirational.
- **qa-diagnose** — Pass 2: after Pass 1's test design is fixed, has full read access to implementation, logs, traces, and metrics to diagnose why a test fails. Independence isn't compromised because the expected behavior was locked in before this role could see the implementation. Can set `REVIEWED` on test results — never `VERIFIED` (a test *passing* is machine-determined and gets `VERIFIED` automatically from CI; a human-legible judgment about test *quality* is `REVIEWED`).
- **security-reviewer** — independent security pass; can set `REVIEWED` with ACCEPT/REJECT. A REJECT from security-reviewer blocks within the security domain; only a human lifts it (see conflict-resolution below). Cannot itself grant `APPROVED`.
- **code-reviewer** — style/maintainability/correctness pass, separate from qa's requirement-level verification. Can set `REVIEWED` — never `VERIFIED`.

**Shared role references:**

`reference/handoff-schema.md` — unchanged structure from v2, with one fix:

```yaml
  inputs:
    - artifact_ref: "repo-a@a1b2c3d:docs/architecture-decision-AD-77.md"
      content_hash: "sha256:9f8e..."
      trust_level: REPOSITORY
```

`artifact_ref` now always resolves to `repo@sha:path` plus a content hash — never a bare filename, which is mutable and therefore not a safe thing to hand off as "the input this decision was based on." Git already versions this; there's no need for a separate artifact registry.

`reference/conflict-resolution.md` **(revised)** — replaces v2's flat authority ranking:

1. **A REJECT from any reviewer blocks within its own domain.** Only a human lifts it. A security REJECT is not overridden by an architecture approval, and vice versa — they're not comparable on one axis, so no single ranking should imply one cancels the other.
2. **Cross-domain disagreement goes to a human**, not to a ranking table. If architect approves and security rejects, that is a human decision, not an automatic outcome.
3. **Upstream-downstream rejection**: rejection evidence goes to the upstream role and the Evidence Ledger. Upstream gets one revision attempt; still rejected after revision → escalate to human with both positions and evidence.
4. **Infeasibility**: product-owner is notified with evidence; Change Set moves to `BLOCKED` until the requirement is revised or confirmed.
5. **Max handoff cycles between any two roles: 3.** After 3 back-and-forth rejections, escalate to human — this prevents infinite rejection loops regardless of the above rules.

`reference/reviewer-diversity.md` **(new)**: for HIGH and CRITICAL tiers, at least one reviewer (security-reviewer, code-reviewer, or architect) must run on a model from a different family than the implementing developer agent, or be a deterministic tool rather than an LLM at all. Same-family models correlate in their blind spots more than different families do; since the platform already spans two tools, this costs nothing extra to arrange.

### 4.8 `/testing`

Unchanged from v2 across test-architecture, web-ui-automation, mobile-automation, api-contract-testing, test-maintenance, performance-testing, and security-testing.

**ai-agent-testing** **(revised)** — mapped onto the **OWASP Top 10 for Agentic Applications** (ASI01–ASI10, published by the OWASP GenAI Security Project) rather than an ad hoc list, so security teams can use a taxonomy they already know:
- *prompt-injection-tests* — tests resistance to instruction injection from untrusted inputs (issue text, README, MCP responses); maps to the content-origin risks in the ASI catalog.
- *tool-misuse-tests* — verifies agents don't use tools outside authorized scope (ASI02: Tool Misuse).
- *agent-authorization-tests* — verifies role-to-tool permission boundaries are enforced, including the qa-derive/qa-diagnose split actually holding under test (ASI03: Identity and Privilege Abuse).
- *policy-bypass-tests* — attempts to bypass binding policy through advisory overrides, control-file manipulation, or creative prompt construction (ASI01: Goal Hijack, ASI09: Human-Agent Trust Exploitation).
- Remaining ASI categories (supply chain, unexpected code execution, memory, inter-agent communication, cascading failures, rogue agents) are consciously deferred — they matter more once third-party skills, long-lived agent memory, and multi-agent parallel execution are actually in use, which is Phase 2+.

### 4.9 `/engineering-design` and 4.10 `/ai-integration`

Unchanged from v2.

### 4.11 `/governance`

**default-permissions**
- `reference/role-tool-permissions.md` **(revised)**:

| Role | Can Read | Can Modify | Can Deploy | Can Set | Restrictions |
|---|---|---|---|---|---|
| developer | repos in Change Set | repos in Change Set scope | No | — | Cannot modify files outside scope; no production access |
| qa-derive | requirements + acceptance criteria + test files | test files only | No | `REVIEWED` on test design | Implementation paths technically denied, not just discouraged |
| qa-diagnose | all repos + test results + logs/traces | test files only | No | `REVIEWED` on diagnosis | Cannot modify implementation code |
| code-reviewer | all repos in Change Set | None | No | `REVIEWED` on code quality | Read-only |
| security-reviewer | all repos + dependency data | None | No | `REVIEWED` (ACCEPT/REJECT) | REJECT blocks within domain; cannot APPROVE alone |
| architect | all repos + contracts | architecture docs only | No | `REVIEWED` on design | Cannot modify implementation code |
| product-owner | requirements + acceptance criteria | requirements only | No | marks `READY_FOR_APPROVAL` | Cannot APPROVE — human-only (see §5.5) |
| **ALL agent roles** | — | — | **No** | **Never**: `APPROVED`, `INTEGRATED`, `RELEASED`, or any control-file write | Enforced via managed settings, not instruction |

- `reference/control-file-policy.md` **(new)**: implements the control-files rule from §4.1 — agent write access to hook configs, agent/skill/MCP definitions, AGENTS.md, CLAUDE.md, CODEOWNERS, rulesets, and CI workflows is denied at the managed-settings layer (organization-controlled, not repo-local). Any such write that does occur (e.g., attempted by a compromised session) is `CRITICAL` tier and requires human approval regardless of source, and is logged via a `ConfigChange`-class hook.

**autonomy-gating** **(new)**
- `reference/verification-strength.md`: the platform's autonomy level for a given repository is gated by that repository's own verification strength — CI reliability and the test coverage of actually-changed code. A repo with weak or absent tests starts in **assist mode** (human reviews every change before merge) regardless of computed risk tier, because `VERIFIED` is only as trustworthy as the tests behind it. Autonomy increases only as the repo's own measured verification strength does.

**permission-scoping**, **policy-drift-check** — unchanged from v2.

---

## 5. Cross-Cutting Design Rules

### 5.1 Evidence taxonomy

Unchanged from v2 — FACT / INFERENCE / ASSUMPTION / PROPOSAL / QUESTION / DECISION / RISK, with `lifecycle_state` (now including `REVIEWED`) tracked separately for DECISION/PROPOSAL entries.

### 5.2 Ask vs. assume

Unchanged from v2.

### 5.3 Fail-safe defaults

| Situation | Default | Never |
|---|---|---|
| Dependency not found by static analysis | UNRESOLVED | "no dependency" |
| Consumer/provider compatibility unknown | INCOMPATIBLE | "assume fine" |
| Risk tier can't be computed | HIGH | LOW |
| Two roles disagree on risk level | Higher assessment wins | Lower assessment |
| Agent uncertain about its own output, matching a named reason code | Escalate risk tier by exactly one level | Proceed at current tier, or escalate more than one level |
| A mandatory capability for the computed tier doesn't exist yet | Route to a named human (Degraded Mode, §2) | Block indefinitely, or silently skip the requirement |

### 5.4 Risk-tiering → gates

| Tier | Example | Gates |
|---|---|---|
| Low | README / docs change | developer + docs check |
| Medium | internal refactor | developer + tests + code-reviewer |
| High | public API change | architect + contract analysis + security-reviewer + code-reviewer |
| Critical | payment schema migration | product-owner + architect + security-reviewer + staged rollout + human release approval |

Human approval requirements by tier and transition are now fully specified in one place — see `/change-management/change-set/reference/approval-matrix.md` (§4.5) — rather than implied differently in three places as in v2.

### 5.5 Authority: REVIEWED, VERIFIED, APPROVED

Three authority classes, not two:

| Value | Who sets it | Basis | Example |
|---|---|---|---|
| **REVIEWED** | An agent role | Judgment, with evidence attached — ACCEPT or REJECT | code-reviewer reviews code quality; architect reviews a design; qa-diagnose reviews a failure |
| **VERIFIED** | The server, from ingested machine evidence only | A deterministic check actually ran and passed | Tests pass (from CI) → VERIFIED. Contract compatible (from compatibility-check) → VERIFIED. SAST clean → VERIFIED. **Never set directly by an agent's own tool call, regardless of role.** |
| **APPROVED** | An authenticated human | Explicit sign-off | `human:tech-lead` approves a plan; `human:release-manager` approves a release |

This replaces v2's two-class model, which let `qa-verifier`, `code-reviewer`, and `architect` "set VERIFIED" on judgment calls — code quality, design soundness — that are not deterministic checks. That collapsed the distinction the whole model depends on: if an LLM's opinion can satisfy the prerequisite for a human's APPROVED, the human isn't actually gating anything a machine couldn't equally have claimed. For HIGH and CRITICAL tiers, `APPROVED` requires `VERIFIED` as a machine-evidenced prerequisite — a human approves on top of verified evidence, not on top of another agent's say-so.

A skill or agent can reach `REVIEWED` or `PROPOSED` — nothing further without a human. This applies as much to `/self-improvement` editing the platform's own skills as it does to a developer role shipping code.

### 5.6 Skill execution model

Unchanged core model from v2 (skills are instruction documents; stateful operations are MCP calls; scripts are tool invocations), plus a mapping table that makes the actual enforcement mechanism for each class of rule explicit, since "the skill says so" and "the platform enforces it" are not the same guarantee:

| Rule | Stated in (skill) | Actually enforced by |
|---|---|---|
| No agent sets APPROVED/INTEGRATED/RELEASED | `/grounding`, §5.5 | MCP server tool surface — no such tool exists for agent callers |
| Untrusted content is data, not instructions | `/grounding/trust-boundaries` | Rule-of-Two session scoping (§5.9) + per-role tool scoping |
| Control files are never agent-writable | `/grounding/trust-boundaries/control-files.md` | Managed settings (org-level) + `PreToolUse` hook |
| QA Pass 1 is implementation-blind | `/roles/qa-derive` | Tool permission denial on implementation paths, not instruction |
| FACT entries are grounded | `/core/fact-classification` | Hooks write FACT entries directly; model never self-reports a FACT |
| Agent identity is authentic | `/core/evidence-ledger` | Server-side derivation from authenticated connection |
| 3-attempt iteration cap | `/grounding/agent-failure-modes` | Orchestrator-enforced counter, scoped by failure class (§4.1) |

Any rule stated in a skill with no corresponding row here is, until it gets one, a guideline the model can choose to follow — not a guarantee. Keep this table current as new rules are added; it's the fastest way to catch the next version of findings 3, 4, and 8 before they ship instead of after.

### 5.7 Agent failure handling

Unchanged core structure from v2, now explicitly cross-referencing the per-failure-class retry policy in §4.1's failure catalog rather than a single flat "3 attempts" rule.

### 5.8 Identity & Authentication

- `agent_role`, `actor_id`, and `trust_level` are always server-derived from an authenticated connection or credential — never accepted as a value the caller supplies.
- One credential per role. A role's MCP tool surface contains only the tools that role is permitted to use; there is no tool, for any role, that writes `APPROVED`, `INTEGRATED`, or `RELEASED`.
- A per-workspace local SQLite ledger is acceptable only for a genuinely single-user, single-workspace pilot. The moment a second person or a cloud-hosted agent session is involved, the ledger moves to a remote, authenticated MCP service.

### 5.9 Trust Boundaries: the Rule of Two

Keyword-based injection detection is not a defense — it's bypassed by paraphrase, encoding, or translation. The structural control: no single agent session combines more than two of the following three properties —
1. Reads untrusted input (issue text, README content, external docs, MCP responses, generated logs).
2. Touches secrets or production data.
3. Can mutate external state or deploy (`EXTERNAL_MUTATION` or `DEPLOY`-class operations).

A developer session reading an issue, with no secrets access, writing only to a branch behind a human-gated PR, has exactly one of three — it passes. A release session with secrets and deploy access but no untrusted input in scope also has exactly two — it passes. Anything that would combine all three gets split into separate sessions or gains an explicit human checkpoint between them.

### 5.10 Forge as Source of Truth

- `INTEGRATED` means an observed merge event on the target branch — ingested by the server from a webhook or CI event, never set by an agent tool call.
- `RELEASED` means an observed deployment record from CI plus an environment approval event.
- Human `APPROVED` means an authenticated human review event — a CODEOWNERS-gated PR review, or an environment approval — ingested by the server, not a tool an agent can call.
- For single-repo work, the issue + PR *is* the Change Set, and the full Change Management MCP server (Server 2) isn't needed until multi-repo or genuinely parallel work makes a custom state machine necessary. This is what keeps Phase 1 lean: most of the state most teams need already exists in a form enterprises, and their auditors, already trust.

---

## 6. MCP Server Design

**Build the stateful engines once, as MCP servers.** Both tools (Claude Code, Copilot) are MCP clients over the same protocol — this is what keeps the heavy machinery genuinely shared rather than duplicated per tool.

**Identity, across all three servers:** every tool call authenticates the caller; `agent_role` and `trust_level` are derived server-side from that authentication, never passed as a trusted parameter. No tool on any server accepts a request to set `APPROVED`, `INTEGRATED`, or `RELEASED` from an agent-authenticated caller.

### Server 1: evidence-ledger-server (Phase 0)

| Tool | Description |
|---|---|
| `record_evidence` | Write an evidence entry. `actor_type`/`actor_id`/`trust_level` are derived from the authenticated connection, never accepted as arguments. Takes: change_set_id, classification, content, source. |
| `query_evidence` | Read evidence entries filtered by change_set_id, actor_role, classification, trust_level |
| `record_incident` | Write a self-improvement incident record (trigger, context, hypothesis, proposal, signal_source) |
| `query_incidents` | Read incidents filtered by skill, pattern, status, signal_source |
| `record_correction` | Write a new entry with `parent_entry_id` set and `outcome_status: CHALLENGED` — the only way to "correct" a past entry |

Persistence: SQLite for single-user/single-workspace pilots; a remote authenticated MCP service once more than one person or any cloud agent session is involved. Entries are append-only and hash-chained.

### Server 2: change-management-server (Phase 2 — multi-repo/parallel only)

| Tool | Description |
|---|---|
| `create_change_set` | Create a new Change Set (requirement, repositories, contracts, parent_id?, depends_on[]?) |
| `get_change_set` | Read Change Set by id, including `tasks[]` and checkpoints |
| `update_status` | Transition status, enforcing valid transitions per lifecycle. **Rejects any attempt by an agent-authenticated caller to set `PLAN_APPROVED`, `INTEGRATED`, or `RELEASED` directly** — those come from `ingest_forge_event` below. |
| `ingest_forge_event` | Record an observed PR merge, CI deploy, or CODEOWNERS review event, and apply the resulting state transition |
| `create_snapshot` | Pin commit SHAs, contract versions, environment state for a Change Set |
| `validate_snapshot_currency` | Check if pinned SHAs are still HEAD; apply path-class overlap rules; report staleness |
| `record_dependency` | Record a discovered dependency (source, target, type, confidence, `evidence_level`: DECLARED / STATIC / OBSERVED) |
| `compute_risk_tier` | Calculate risk tier, applying reason-code-gated escalation rules |
| `record_handoff` | Store a typed handoff contract between roles |

Persistence: same workspace database as Server 1 (separate tables). Not needed at all for single-repo work handled via Server 1 + forge events directly (§5.10).

### Server 3: contract-registry-server (Phase 3)

| Tool | Description |
|---|---|
| `register_contract` | Register a contract (id, provider, consumers, spec, type, compatibility_policy) |
| `check_compatibility` | Check compatibility between two versions, in both directions for event contracts, against **actually recorded deployed versions** |
| `detect_drift` | Compare declared contract against observed reality |
| `record_deployment` | **(new)** Record which application version is deployed to which environment, fed by CI — the data source `check_compatibility` needs to check against real deployed state rather than assuming "latest against latest" |

Persistence: same workspace database.

---

## 7. Pilot & Measurement

Nothing above means anything if there's no way to tell whether it's actually helping. Before a pilot starts:

- **Baseline five numbers** on the pilot repo(s) before the platform touches them: lead time, change-failure rate, rework rate, review time per PR, and cost per merged change.
- **Track the human-override rate** — both risk-tier downgrades (§4.5) and any case where a human overrides an agent's recommendation. A rising override rate is an adoption-health signal, not noise to average away.
- **Cap change size in risk-tiering.** Above a configured diff size, decompose before implementing — AI-assisted changes readily produce large diffs that are hard to review well, which is a known driver of exactly the instability and rework that erases throughput gains.
- **Gate autonomy on verification strength, not just risk tier** (§4.11 autonomy-gating). A repo with unreliable CI or thin test coverage on changed code starts in assist mode regardless of how low-risk a change looks, because `VERIFIED` only means what the tests behind it mean.
- **Write exit criteria before starting**, not after. Define what "the pilot succeeded" and "the pilot failed" mean, in terms of the five baseline numbers, before the first Change Set runs.

---

## 8. Tool Compatibility — Claude Code / GitHub Copilot

**AGENTS.md — corrected precedence.** Claude Code added AGENTS.md support in v2.1.277 (September 18, 2026), but strictly as a **fallback**: it's read only when no `CLAUDE.md` or `CLAUDE.local.md` exists at or above the working directory. If a `CLAUDE.md` is present, it wins and AGENTS.md is ignored, unless the `CLAUDE.md` explicitly imports it (`@AGENTS.md`) or the `instructionFiles` setting is `claude-md-and-agents-md`. Versions 2.1.277–2.1.279 additionally had a bug where AGENTS.md only loaded with telemetry on — fixed in 2.1.280. **Practical consequence:** don't rely on "both tools read AGENTS.md natively" as an unconditional fact. Keep AGENTS.md as the source of truth, generate a one-line `CLAUDE.md` (`echo '@AGENTS.md' > CLAUDE.md`) beside each one, and add a CI check verifying both exist and the import is intact. This also gives you a log of which instructions were actually in effect, since an imported file fires an `InstructionsLoaded`-class hook where a directly-read AGENTS.md does not.

**Critical trust constraint:** `AGENTS.md` is a repository file with REPOSITORY trust level (§4.1). It provides project-specific guidance — coding standards, architecture notes — but cannot override platform safety policy, approval rules, trust boundaries, or mandatory skill bindings. Binding policy lives in platform skills and hooks, delivered through **managed settings**, not in a file any repo contributor can edit.

| Concept | Claude Code | GitHub Copilot |
|---|---|---|
| `/skills/*` | Native Skills feature — `SKILL.md` + frontmatter | `.github/skills/*.md` with reusable `SKILL.md` structures, now a first-class capability |
| `/roles/*` | Subagents — `.claude/agents/*.md` | Custom agents — `.github/agents/*.agent.md`; supports agent-to-agent flows |
| `/grounding/*`, `/enforcement/*` | Hooks — `.claude/hooks/` + `settings.json` (project scope) or **managed settings** (org scope, required for control-file protection); `PreToolUse`/`PostToolUse`; blocks via exit code 2 or `permissionDecision: deny` | Hooks — `.github/hooks/` + `hooks.json`; `preToolUse`/`postToolUse`; same `permissionDecision: deny` contract |
| `/skill-routing/token-budget-optimizer` | Model-per-task, moving instructions from CLAUDE.md into skills, delegating verbose work to subagents | Modular path-scoped `.github/instructions/`, per-agent model/MCP scoping |
| `/governance/default-permissions` | Subagent tool restrictions in frontmatter; MCP scoping per agent; **managed settings** for control-file denial | `.agent.md` tool configuration; per-agent MCP scoping |
| Stateful engines (Servers 1–3) | MCP client | MCP client |
| Handoff contracts | Platform-level via MCP; Claude subagent delegation is the runtime delivery | Platform-level via MCP; **note: handoffs are not supported for Copilot cloud agent on GitHub.com** — use MCP as the durable handoff mechanism there rather than the native handoff feature |

**Known asymmetry:** Claude Code's hook system has many more lifecycle events than Copilot's smaller, newer set (`sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred`). Design `/grounding`, `/enforcement`, and `/self-improvement` detection logic against that common subset as the portable core. Treat any additional Claude Code event as a tool-specific enhancement, not a dependency — and verify the exact current event name against Claude Code's own hook reference before building against it; not every event name that circulates is necessarily current or correctly named.

**Packaging:** both tools support bundling skills + agents + hooks + MCP into an installable unit. Each top-level folder in §3 is a natural plugin boundary, **including `/enforcement`, which should ship from a managed/organizational source, not as an editable part of each repo's own plugin install** — that's the whole point of finding 1's fix.

**Practical build step:** author each role/skill once in a tool-neutral spec, then generate `.claude/agents/*.md` and `.github/agents/*.agent.md` from it. The frontmatter fields differ slightly between the two — hand-maintaining both copies will drift.

---

## 9. Build Sequence

1. **Control-files definition + managed-settings denial** — before anything else runs, agents must already be unable to write to hooks, agent/skill/MCP config, AGENTS.md, CODEOWNERS, rulesets, or CI workflows.
2. **`AGENTS.md` tree** (root + nested) as the repository-guidance layer, with the one-line `CLAUDE.md` shim beside each, and a CI check confirming both exist.
3. **`/core` + `/grounding` + `/enforcement`** — evidence-ledger (full schema, authenticated, hash-chained), fact-classification, evidence-gate, ambiguity-escalation, trust-boundaries (including control-files), agent-failure-modes (with per-class retry policy), human-review-format. Nothing else produces output without this in place.
4. **Evidence Ledger MCP server** (Server 1), with identity derived from the authenticated connection from day one — not retrofitted later.
5. **The lightweight path-based risk-tier lookup** (§2, Phase 0) — so nothing in Phase 1 can ever be stuck unable to compute a tier before the full risk-tiering capability exists.
6. **`/governance/default-permissions`** — including the hard rule that no agent-callable tool anywhere sets APPROVED, INTEGRATED, or RELEASED.
7. **`/skill-routing`** — two-phase routing with Phase 2 able to re-run mandatory bindings, binding-vs-advisory, token-budget-optimizer.
8. **Minimum `/roles`**: developer, qa-derive, qa-diagnose, code-reviewer — plus handoff-schema and the revised conflict-resolution. Single-repo Change Sets run forge-native from here (§5.10) — no Server 2 yet.
9. **`/self-improvement`** — with the positive-signal quality gate and the REVIEWED→APPROVED pipeline for its own candidate revisions.
10. **`/testing/security-testing` + `/testing/ai-agent-testing`** (OWASP ASI-mapped) — in place before the platform runs with any real autonomy.
11. **`/change-management` + Change Management MCP server (Server 2)** — built when multi-repo or genuinely parallel work first requires it, not before. Includes tasks/checkpoints, the approval matrix, path-class staleness, reason-coded risk escalation, operation classes, worktree-per-task.
12. **Populate `/testing`, `/engineering-design`, `/ai-integration`** progressively, routed in via risk-tiering as real tasks need them.
13. **`/contracts` + Contract Registry MCP server (Server 3, with `record_deployment`) + remaining `/roles` and `/governance`** — once real cross-repo Change Sets are happening and the dependency patterns are known.
14. **Baseline the five pilot metrics (§7) before the first real Change Set runs**, and write exit criteria down before you need them.
15. **Tool-specific generation step** — the generator that emits `.claude/agents/*.md` and `.github/agents/*.agent.md` from the tool-neutral role specs.
