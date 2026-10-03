# ADR 0002 — Product Planning layer (Epic / Story / Milestone, DoR, DoD)

- **Status:** Proposed. A human must approve it, because it changes platform policy.
- **Date:** 2026-10-03
- **Normative spec:** [plan v3.1 §4.12](../ai-sdlc-platform-plan-v3.1.md#412-product-planning)

## Context

v3 starts at the Change Set. Upstream of it the plan has only fragments: product-owner
"turns ambiguous requests into scoped requirements", `READY_FOR_APPROVAL`, and acceptance
criteria that qa-derive is supposed to derive tests from. There is no defined artifact for
an epic, story or milestone. There is also no acceptance-criteria format, no Definition of
Ready, no Definition of Done, and no gate between "someone asked for X" and "a developer
agent is changing code".

An external review, written against v2, proposed a Product Planning layer. Its diagnosis
still holds for v3. This ADR records what we adopted, what we changed and why. The goal is
to keep the layer consistent with v3's existing principles: forge as source of truth,
three authority levels, the Rule of Two, "skills inform, hooks enforce", and lean by default.

## Assessment of the review

### Adopted as proposed
| Proposal | Why it's right |
|---|---|
| A dedicated planning layer upstream of the Change Set | Without it, qa-derive has no stable acceptance-criteria contract to derive from, and "acceptance criteria actually exercised" (the self-improvement positive-signal gate in §4.2) cannot be measured. |
| Separate story *creation* from story *refinement* | These are different activities run by different people. Refinement is the three-amigos loop: planner, qa-derive and developer. |
| DoR/DoD as **machine-readable policy** checked by a gate, not just a checklist inside a skill | This is v3's own principle: a skill is guidance, a gate is enforcement. |
| Mandatory / conditional / optional criteria, selected by story type | Scales process to risk (§1). A docs story must not face the same 21-item DoR as a payment migration. |
| Typed stories (`FEATURE`, `SPIKE`, `DATA_MIGRATION`, …) | Type is a cheap, early signal for which gates and roles apply. |
| Many-to-many Story ↔ Change Set | Real cross-repo work needs it, and it matches v3's multi-repo Change Set. |
| A dedicated planner role separate from product-owner | It stops product-owner from becoming a do-everything agent. Accountability for intent stays apart from decomposition work. |

### Adopted with changes
| Proposal | Problem | What we did instead |
|---|---|---|
| Linear hierarchy *Requirement → Epic → Milestone → Feature → Story → Task* | It mixes two different axes. A milestone is an outcome checkpoint in time, not a level of scope, and its stories often come from several epics. A 7-level tree also contradicts v3's deferral of the "Full Portfolio/Program hierarchy". | **Scope tree:** Requirement → Epic → (Feature, optional) → Story. **Separate time axis:** Milestone and Release, which group items from the tree many-to-many. **Task** is the *existing* `tasks[]` entry inside the Change Set (§4.5), not a second Task concept. |
| Stories as "typed ADLC artifacts" (storage not specified) | If agents write stories straight into a tracker, that is an `EXTERNAL_MUTATION` by a session that just read untrusted requirement text. That breaks the Rule of Two (§5.9). Tracker items are also mutable, so a handoff cannot pin them as `repo@sha:path`. | **Plan-as-code.** Planning artifacts are YAML files under `plans/`, authored by agents through a PR (`REPO_WRITE`) and merged by humans. A CI job (SYSTEM identity) projects them into GitHub Issues or Jira. Acceptance criteria become hash-pinnable and diff-reviewable. |
| DoR gate moves the story to `READY` | The review treats every DoR item as machine-checkable. Many are judgments, for example "acceptance criteria are testable" or "the story is small enough". If a gate passes those, it is laundering an agent's opinion into a `VERIFIED`, which is the exact collapse v3 fixed in §5.5. | Each DoR/DoD item declares a **check kind**: `STRUCTURAL` (deterministic, produces VERIFIED), `JUDGMENT` (a named role must record REVIEWED/ACCEPT) or `APPROVAL` (a named `human:` approver, by tier). The gate checks that the right kind of evidence exists. It never makes the judgment itself. |
| `READY` / `DONE` as story states | If status lives in an editable field, an agent can simply write `status: READY`. | Plan files carry **no status field**. Status is derived by the gate and the server, recorded in the ledger and shown in the tracker by CI. No agent tool can set `READY`, `DONE` or `ACCEPTED`. |
| Acceptance criteria "exist and are testable" | "Exist" is too weak to trace against. | An **acceptance-criteria standard**: each criterion has an ID (`ST-101/AC-2`), uses Given/When/Then, and has a `kind` (functional / negative / nfr) and a `verification` (automated / manual). Tests tag the AC IDs. AC coverage becomes a machine check (VERIFIED). |
| A dependency-discovery skill inside planning | It duplicates `/change-management/dependency-discovery`. | A **dependency-mapper** for story-level dependencies that *reuses* the existing scanners. Fail-safe: unknown means UNRESOLVED. |
| An ambiguity-resolution skill inside planning | It duplicates `/grounding/ambiguity-escalation`. | Planning skills reference the grounding skill. They do not redefine it. |

### Rejected or deferred
| Proposal | Reason |
|---|---|
| Product vision, roadmap-planner, portfolio levels | v3 already defers these until more than one team shares requirements across systems. That still applies. |
| Sprint planning, capacity, sprint goals, velocity | Commitment and capacity belong to humans. The platform *reads* the team's sprint or iteration from the tracker and plans nothing. Agent-generated story points are not calibrated. We size by **predicted diff size** instead, tied to §7's change-size cap, and calibrate against actual diffs. |
| Release-ready gate | Already covered: `RELEASED` comes from forge/CI events plus the approval matrix (§4.5, §5.10). A second release gate would add a competing source of truth. |
| A separate "Feature Creator" skill | Features are an optional grouping, and the epic-decomposer handles them. If they turn out to need their own skill, that gets a new ADR. |
| A full Work Graph service in Phase 1 | Phase 1 runs on plan files and the forge. A `work_planning` module of the `adlc` MCP server arrives in Phase 2, alongside multi-repo Change Sets. |

### Added beyond the review
1. **Freeze acceptance criteria at READY.** When a story becomes READY, the gate records a hash of its acceptance criteria. If the criteria change after that, the story goes back to `REFINING`, and qa-derive's earlier test-design REVIEWED is invalidated. Without this, qa-derive's "expected behaviour locked before seeing the implementation" guarantee (§4.7) can be bypassed by editing the criteria mid-flight.
2. **qa-derive starts during refinement.** The best proof that criteria are testable is qa-derive producing a test outline from them, without seeing the code. That outline is both the DoR JUDGMENT evidence and Pass 1's starting input.
3. **Story type can only raise the risk tier, never lower it.** Each type has a tier floor. The effective tier is `max(type floor, path-based tier, computed tier)`. If a story declared `DOCUMENTATION` touches code paths, the actual diff decides the tier and the mismatch is flagged as a scope violation.
4. **Spikes have their own DoD.** The output is a DECISION or ADR, findings, and follow-up stories. No production code from a spike branch is merged.
5. **Degraded mode for product-owner.** The product-owner agent role is Phase 3, but planning arrives in Phase 1. Until then, scope approval for HIGH/CRITICAL stories goes to `human:product-owner` (§2 Degraded Mode).
6. **Planning metrics** for §7 and for self-improvement:
   - DoR escape rate: READY stories that later hit a blocking QUESTION or go back to REFINING.
   - Split rate after READY.
   - Size-estimate calibration: predicted versus actual diff.
   - AC coverage ratio.
7. **Planning policies are control files.** `skills/product-planning/policies/**` (story types, DoR, DoD) is added to the control-file list. An agent that can weaken the DoR has no DoR.

## Consequences
- Phase 1 gains: the `product-planner` role; requirement-intake, story-writer, story-refinement, definition-of-ready and definition-of-done; the policies; and CI gates (`plan-lint`, `readiness-gate`, `completion-gate`, `ac-coverage`).
- Phase 2 gains: epic-decomposer, milestone-planner, dependency-mapper, the `work_planning` MCP module, and story↔Change Set many-to-many in Server 2.
- The Change Set schema gains `story_refs[]`, and each task gains `ac_refs[]`.
- Cost: one more PR per planning round. This is deliberate. Plan review is where the cheapest defects get caught.
