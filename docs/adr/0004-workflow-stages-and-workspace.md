# ADR 0004: Enter at any stage, stop at any stage; find or create the workspace

- **Status:** Proposed. Requires human approval.
- **Date:** 2026-10-03
- **Normative spec:** [plan v3.1 §4.14](../ai-sdlc-platform-plan-v3.1.md#414-workflow-stages--workspace-resolution)

## Context
The primary use case: *"our requirement documents are ready — ingest them, create all the related documents, and continue through architecture and planning."* Users may equally arrive with architecture docs, a backlog, or existing code.

Users don't start every piece of work from a blank requirement. Typical requests look like this:
- "Here are my Jira stories, implement ST-40."
- "Only plan this epic. Don't write code."
- "Write tests for this existing service."
- "Take this from design through to the PR."

Each skill was written as if the work before it had already happened and as if the right repositories were already open. In practice, the inputs may already exist somewhere (a tracker, docs, an existing test suite), may be missing, or the repo itself may not exist yet.

**Terminology.** *Phases 0–3* (§2) describe the order in which the **platform is built**. *Stages* describe a piece of **work's** path through the lifecycle. They are separate concepts.

## Decision

### 1. A stage graph with entry and exit contracts
```
INTAKE → ARCHITECTURE → PLAN → DESIGN → IMPLEMENT → TEST → REVIEW → INTEGRATE → RELEASE → LEARN
```
Each stage declares the following in `skills/workflow/stages.yaml`, which is machine-readable:
- its **required inputs**, as artifact kinds (for example a READY story or a frozen test design);
- its **outputs**;
- its **exit gate**, the existing CI or policy gate;
- the roles and skills involved.

INTEGRATE and RELEASE are observed forge/CI events (§5.10). A user can run up to them but never "performs" them.

### 1a. Architecture precedes planning; documents are a first-class entry
- **ARCHITECTURE** is a solution-level stage between INTAKE and PLAN: service boundaries, contracts and repos decide how epics and stories should be cut. Story-level **DESIGN** remains after READY.
- **INTAKE from documents** (`requirements-ingestion`): source register with content hashes, requirements, NFR catalog, glossary/domain model, personas, constraints, open questions, and a doc-section → REQ traceability matrix. Ingested text is data, never instructions; contradictions become blocking QUESTIONs citing both sources; re-ingestion diffs by section hash.
- ARCHITECTURE outputs the service/repo map, which feeds workspace resolution (§4 below) — this is where "create the repos we need" is first known.

### 2. Run from any stage to any stage, but never skip the gates in between
The user can name any start stage and any end stage, or a single stage. The conductor skill (`/adlc`) does three things:
1. **Preflight the start stage.** For each required input, the result is one of the following:
   - `SATISFIED`: the input exists and its gate passed.
   - `ADOPT`: the input exists outside the platform (tracker items, docs, existing tests or code). It is imported as DRAFT with source trust levels, and then the gate runs on it.
   - `BACKFILL`: the input is missing. The conductor proposes the smallest upstream run that would produce it.
   - `ASK`: the input is ambiguous. One batched QUESTION is raised, with candidate answers already filled in (never ask empty-handed).
   - `BLOCK`: a gate failed on existing evidence. The conductor reports exactly what is missing.
2. **Run the stages in order**, from the start stage through to the end stage. Every stage's exit gate applies. Starting late never turns a gate off. If earlier stages' inputs are already SATISFIED, starting later simply skips work that is already done.
3. **Stop at the end stage** with a checkpoint: a ledger cursor, a handoff, and the next stage's preflight result. "Resume from X" then picks up from that checkpoint.

The amount of backfill scales with risk, consistent with §1 and v3.1's inline-story exception:
- A LOW-tier `BUG_FIX` or `DOCUMENTATION` change entering at IMPLEMENT can use an inline story in the PR body.
- A HIGH-tier change entering at IMPLEMENT without a READY story gets `BACKFILL: PLAN (refinement only)`. The code is never written first.

### 3. Characterization mode for "test this existing code"
If a user enters at TEST and no AC or test design exists, the only oracle available is the code's current behaviour. That is allowed only when it is labeled honestly:
- The tests are tagged `characterization`.
- An ASSUMPTION is recorded: "current behaviour is the intended behaviour".
- They are **not** counted as AC verification.
- They are not used for VERIFIED on any story.

This keeps the rule from ADR 0003 that code is not the oracle, while still supporting legacy coverage work. Adding AC later lets those tests graduate into AC-traced tests.

### 4. Workspace resolution: find, ask, or create
Every stage begins by resolving the workspace with `resolve_workspace.py`. The search order is:
1. repositories the user names explicitly (path or URL);
2. `adlc.workspace.yaml` in the current directory or a parent directory;
3. the current git repository, plus sibling git repositories in the parent directory;
4. references in existing artifacts (`plans/` `source_refs`, Change Set `repositories`, git remotes).

Every repository the search finds is checked against the repository roles that stage needs:
- `app`
- `planning` (in a single repository, `plans/` sits inside the app repo by default)
- `tests` (when E2E tests live in their own repository)
- `contracts`
- `infra`

Each role then resolves to one of three outcomes:
- **Found:** recorded as FACT with `repo@sha`.
- **Ambiguous:** raised as one QUESTION listing the ranked candidates.
- **Missing:** the user gets two creation options.
  - **Local** (`WORKSPACE_WRITE`, which agents may do): `git init`, the folder skeleton, a `plans/` tree, and a draft `adlc.workspace.yaml`.
  - **Remote** (`EXTERNAL_MUTATION`, which agents never do): the agent writes a `repo-request.yaml` (name, owner team, visibility, template, branch protection, CODEOWNERS owner). A human runs `create_repo_from_request.py`, or an approved CI workflow does. The new repository is created from the platform's `templates/repo-bootstrap/`. That template ships the control files (AGENTS.md plus the CLAUDE.md shim, CODEOWNERS, CI), because agents must never author those files.

`adlc.workspace.yaml` is a *map*, not a grant. Scope always comes from the Change Set and role permissions, so editing the manifest cannot widen what any agent is allowed to touch.

### 5. Every skill is self-sufficient at entry
Each SKILL.md declares the following in its frontmatter `metadata`:
- `stage`
- `inputs`
- `outputs`
- `repo_roles`

Each one also begins with a standard **Preflight** section that points to `/workflow/stage-preflight`. This lets any skill be invoked directly, for example "just write stories for this", without the conductor, and still resolve the workspace and adopt, backfill or ask correctly.

## Rejected alternatives
- **Free skipping of earlier stages when the user asks.** That would turn "start at IMPLEMENT" into a way around the DoR and test-oracle rules. Instead, earlier stages are skipped only when their gates are already satisfied by evidence.
- **Agents creating remote repositories with an org-admin token.** That breaks the Rule of Two and the control-file rules. Remote creation is always done by a human or by CI.
- **Treating the workspace manifest as a control file.** That would stop agents from even drafting it. Keeping it permission-neutral is the safer design.

## Consequences
- New skill group `/workflow`:
  - `adlc-conductor`
  - `requirements-ingestion` (+ `ingest_documents.py`)
  - `workspace-resolver`
  - `stage-preflight`
  - `brownfield-adoption`
  - `repo-bootstrap`
- New scripts: `resolve_workspace.py`, `stage_preflight.py`, `create_repo_from_request.py` (run by humans or CI).
- New supporting files: the `stages.yaml` stage graph and two schemas (workspace manifest, repo request).
- Every existing SKILL.md gains the four metadata fields and a Preflight section.
- User entry points:
  - Claude Code: `/adlc`, plus each skill's own `/name`.
  - Copilot: `.github/prompts/adlc.prompt.md`, generated by the role generator.
