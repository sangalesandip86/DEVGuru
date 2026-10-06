---
name: adlc-conductor
description: Run work through the ADLC lifecycle (/adlc) -- any stage range with every gate. Use for ingest, plan, implement, test, or resume requests.
metadata:
  group: workflow
  phase: 1
  binding: false
  plan-ref: "§4.14"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: [planning, app]
---

# ADLC Conductor (`/adlc`)

## Purpose
Users start work from wherever they are: a folder of requirement documents, a Jira backlog,
existing code, or a half-finished plan. The conductor turns that request into a **ranged run**
over the stage graph ([`stages.yaml`](../stages.yaml)):

```
INTAKE → ARCHITECTURE → PLAN → DESIGN → IMPLEMENT → TEST → REVIEW → INTEGRATE* → RELEASE* → LEARN
                                                   (* observed forge/CI events: run up to them, never perform them)
```

It does three things:
1. **Preflights** the start stage.
2. **Runs** every stage from the start stage to the end stage, in order, with each stage's exit gate.
3. **Stops** with a checkpoint, so "resume from X" works later.

> **Stages are not build phases.** *Build phases 0–3* (plan §2) describe the order in which the
> platform itself is built. *Stages* describe a piece of work's path. If a stage's lead agent role
> is not built yet in the current build phase, the stage routes to the named human in
> `stages.yaml → degraded_mode` (for example `architect → human:tech-lead`). That routing is
> recorded as the role's handoff target and is never treated as a block (plan §2 Degraded Mode).

## When this applies
- Any request that names lifecycle work and a starting point or end point, or that should flow
  across more than one stage.
- A user invoking a single skill directly (for example "just write stories for REQ-3") does **not**
  need the conductor. Every skill has its own Preflight, so direct invocation is safe.

## Preflight
1. Resolve the workspace for **every** stage in the range. Run
   [`resolve_workspace.py`](../workspace-resolver/scripts/resolve_workspace.py) with the union of the
   stages' `repo_roles`.
2. Run [`stage_preflight.py`](../stage-preflight/scripts/stage_preflight.py) `--start <X> --end <Y>`
   for the start stage. Pass `--story`, `--tier`, `--mode` and `--adopt` as parsed from the request.

## Procedure
1. **Parse the request** into `start`, `end`, `story`, `mode` and `adopt[]`, using
   [reference/request-grammar.md](reference/request-grammar.md).
   - If the request names no start stage, infer it from what the user hands over. Documents mean
     INTAKE, a READY story means DESIGN or IMPLEMENT, code with no stories means TEST in
     characterization mode.
   - If you can't infer it, raise **one** QUESTION with a proposed default
     ([never ask empty-handed](../../grounding/ambiguity-escalation/SKILL.md)).
2. **Resolve the workspace.** For each repo role, act on the resolver's result:
   - `FOUND`: record the role and its `repo@sha`.
   - `AMBIGUOUS`: ask, listing the ranked candidates.
   - `MISSING`: offer three options: point to an existing path, `--init-local` (an agent may do
     this), or `--request-remote`, which a human or CI executes through
     [repo-bootstrap](../repo-bootstrap/SKILL.md).
3. **Preflight the start stage** and act on each input's outcome
   ([stage-preflight](../stage-preflight/SKILL.md)):
   - `SATISFIED`: nothing to do.
   - `ADOPT`: run [brownfield-adoption](../brownfield-adoption/SKILL.md). The imported items are
     DRAFT, and the stage gate then runs on them.
   - `BACKFILL`:
     - Propose extending the run backwards to the named stage. Use the smallest run that works,
       for example "PLAN (refinement only)".
     - LOW-tier `BUG_FIX` or `DOCUMENTATION` changes may use the inline-story mode instead.
     - At HIGH or CRITICAL, **never write code first.**
     - `RUN_CONVENTION_SCAN` means run `convention_scan.py` now. It is cheap and has no side effects.
   - `ASK`: raise one batched QUESTION for the whole run, with every open choice and its proposed default.
   - `BLOCK`: stop. Report the exact missing items and write a checkpoint with `stop_reason: BLOCKED`.
4. **Run each stage in order.** For each stage:
   - Load the stage's `skills` through [skill-routing](../../skill-routing/skill-router/SKILL.md).
     Routing may add mandatory bindings. It never removes them.
   - Act as, or hand off to, the stage's `lead_roles`. On existing code, ARCHITECTURE, DESIGN and
     IMPLEMENT follow the project's own standards
     ([project-conventions](../../engineering-design/project-conventions/SKILL.md), §4.15).
   - Produce the stage's documents (the `documents` list in `stages.yaml`) through PRs in the
     resolved repos.
   - Run or await the stage's `exit_gate`.
     - A failed gate stops the run with `GATE_FAILED` and lists the failing items.
     - A gate that needs a human (an APPROVAL) stops the run with `ASK_PENDING` and names the approver.
   - Preflight the next stage before starting it. Its inputs should now be `SATISFIED`.
5. **Never skip a gate between the start and end stages.** Starting late only skips *work* whose
   gate has already passed on existing evidence. The CI gates themselves (readiness, completion,
   integrity, coverage) enforce this regardless of what the conductor does.
6. **Observed stages.** INTEGRATE and RELEASE are facts the server observes, such as a merge or a
   deployment plus its approval. The run ends with `OBSERVED_STAGE` and names the event it is waiting for.
7. **Write the checkpoint** to `.adlc/runs/<run_id>/checkpoint.json`, following the
   [checkpoint schema](../schemas/checkpoint.schema.json):
   - completed stages;
   - artifacts as `repo@sha:path` plus content hash;
   - the ledger cursor;
   - the handoff, recorded through `mcp:adlc.record_handoff`;
   - open questions;
   - the next stage's preflight result.

   Tell the user in 3–6 lines: what was produced, where it is, what is open, and the exact phrase to resume.
8. **Resume.**
   1. Read the checkpoint.
   2. Re-resolve the workspace, because SHAs may have moved.
   3. Re-run the preflight of `stopped_at`. A stale snapshot or a changed AC hash shows up there as
      BACKFILL or BLOCK.

## Outputs
- The run checkpoint, plus ledger entries:
  - a DECISION for the parsed run plan;
  - QUESTIONs (batched);
  - a handoff at each stage boundary.
- The stage artifacts themselves are produced by the stage skills, not by the conductor.

## Enforcement
**Enforced** (partial) — some rules are structural, others are guideline only.

- **Gates between stages** are enforced by CI and the server, not by this skill:
  - `plan_lint.py`, `readiness_gate.py`, `completion_gate.py`, `ac_coverage.py` and the test-integrity checks;
  - the forge events behind INTEGRATE and RELEASE (§5.10).
- **No agent sets READY, DONE, ACCEPTED, INTEGRATED or RELEASED.** No agent tool exists for those
  states (plan §5.6).
- **Remote repo creation** is human or CI only (`create_repo_from_request.py` interlock; agents hold no org token).
- **Parsing the request and choosing the smallest backfill** are guidelines. A misparsed range
  cannot bypass a gate. It can only waste work.

## Standalone Mode (outside DEVGuru repo)

When the ADLC skills infrastructure (`skills/` tree) is not present in the current project:

1. **Do not run** `resolve_workspace.py` or `stage_preflight.py` — these require the skills tree.
2. **Use the embedded stage graph** above to orchestrate work through stages.
3. **Delegate to agent roles directly** using `@developer`, `@architect`, `@code-reviewer`, etc.
4. **Skip CI gate scripts** that depend on the skills tree. Record evidence through MCP tools when available.
5. The MCP server tools (`mcp__adlc__*`) work from any project when installed globally (`--scope user`).

### Standalone Preflight Checklist

In standalone mode, use this lightweight checklist instead of `stage_preflight.py`. Before entering
each stage, verify the required artifacts exist:

| Stage | Required Artifacts | Check |
|-------|--------------------|-------|
| INTAKE | User request or requirement document | A `.md`, `.yaml`, or `.txt` file describing what to build exists in `docs/` or was provided inline. |
| ARCHITECTURE | Requirement reviewed by product-owner | `docs/` contains a PO assessment or the requirement is marked READY_FOR_APPROVAL. |
| PLAN | Architecture decisions recorded | `docs/architecture.md` or equivalent ADR exists. |
| DESIGN | Stories with acceptance criteria | `docs/stories.md` or story files exist with typed stories and ACs. |
| IMPLEMENT | Stories are READY with passing preflight | Stories exist, architecture is decided, and no BLOCK conditions remain. |
| TEST | Implementation exists with unit tests | Source code and at least one test file exist. Tests pass. |
| REVIEW | Tests pass, implementation complete | `python -m unittest` (or equivalent) exits 0. All stories' ACs are addressed in code. |

If a required artifact is missing, either **backfill** (extend the run backwards) or **block** with
a clear message naming the missing items.

### Standalone Conductor Hygiene

When running in standalone mode:

- **Add `.claude/worktrees/` and `__pycache__/` to `.gitignore`** before dispatching agents.
- **Ensure at least one commit** exists before dispatching agents in worktree isolation (empty repos cause `git rev-parse HEAD` failures).
- **Copy artifacts from worktrees** to the main tree after each agent completes, then the worktree can be cleaned.
- **Persist review outputs** from read-only agents (code-reviewer, security-reviewer) — they cannot write files themselves. Save their handback content to `docs/`.

## References
- [reference/run-examples.md](reference/run-examples.md): worked scenarios.
- [reference/request-grammar.md](reference/request-grammar.md) · [reference/checkpoint-format.md](reference/checkpoint-format.md)
- [../stages.yaml](../stages.yaml) · [stage-preflight](../stage-preflight/SKILL.md) · [workspace-resolver](../workspace-resolver/SKILL.md)
- [requirements-ingestion](../requirements-ingestion/SKILL.md) · [brownfield-adoption](../brownfield-adoption/SKILL.md) · [repo-bootstrap](../repo-bootstrap/SKILL.md)
- [grounding/evidence-gate](../../grounding/evidence-gate/SKILL.md) · [grounding/ambiguity-escalation](../../grounding/ambiguity-escalation/SKILL.md)
