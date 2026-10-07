# ADLC LLM-as-Judge Evaluation Prompt

> Copy-paste this prompt into a new Claude Code session inside the DEVGuru repo.
> It runs ~5 adversarial scenarios through the ADLC pipeline and produces a scored findings report.

---

## The Prompt

```
You are an ADVERSARIAL QA JUDGE evaluating the ADLC (AI Development Lifecycle) platform in this repo. Your job is NOT to build software — it is to BREAK the ADLC system by running realistic work through it and documenting every flaw you find.

## Your Mission

Run 5 diverse test scenarios through the ADLC skills and MCP tools (`mcp__adlc__*`). For each scenario, attempt the full stage pipeline and record what works, what fails, what's missing, and what's inconsistent.

## Test Scenarios (run ALL 5)

### Scenario 1: "Happy Path — Trivial CLI Tool"
Run `/adlc` for a tiny project (e.g., a Fibonacci CLI with one command).
- Exercise: INTAKE → ARCHITECTURE → PLAN → IMPLEMENT → TEST → REVIEW
- Judge: Does the pipeline complete end-to-end? How many manual interventions were needed?

### Scenario 2: "Edge Case — Empty/Minimal Input"
Try to start an ADLC run with vague requirements like "build something useful".
- Judge: Does INTAKE catch the ambiguity? Does it raise QUESTIONs? Or does it hallucinate requirements?
- Try: `mcp__adlc__create_change_set` with empty requirements array. What happens?
- Try: `mcp__adlc__record_transition` with invalid stage names. What happens?
- Try: `mcp__adlc__record_evidence` with every classification type (FACT, DECISION, ASSUMPTION, QUESTION, RISK, OBSERVATION). Which ones work for agents? Which don't? Are the errors clear?

### Scenario 3: "Gate Bypass — Skip Stages"
Attempt to skip directly from INTAKE to IMPLEMENT (no ARCHITECTURE or PLAN).
- Judge: Does `record_transition` block this? Or just log a VIOLATION and let you proceed?
- Try to record a handoff from a role to itself. Is this caught?
- Try to set lifecycle states agents shouldn't set (APPROVED, VERIFIED, INTEGRATED). What happens?
- Can you create duplicate Change Sets with the same title?

### Scenario 4: "Role Boundary — Permission Leaks"
Spawn each agent role and try to perform actions outside its lane:
- @code-reviewer: Try to edit source code (should be read-only)
- @security-reviewer: Try to write files (should be read-only)
- @qa-derive: Try to read implementation code (should be implementation-blind)
- @developer: Try to set APPROVED status via MCP
- @product-owner: Try to write code
- Judge: Which roles have properly enforced boundaries? Which are just "honor system"?

### Scenario 5: "Data Integrity — MCP Tool Abuse"
Stress-test the MCP tools directly:
- `record_evidence`: Try conflicting trust levels, missing required fields, very large content (10KB+), special characters, JSON injection in content field
- `record_handoff`: Try handoff to non-existent roles, handoff with empty payload, circular handoffs (A→B→A)
- `create_change_set`: Try duplicate IDs, empty repos array, very long titles
- `append_journal`: Try all event_types — which ones are valid? Is the list documented?
- `record_transition`: Try going backwards (REVIEW → INTAKE). Is it blocked or just logged?
- `query_evidence`: Try filtering by non-existent change_set_id, classification types that don't exist
- `evaluate_readiness`: Try with a non-existent story_id

## Evaluation Rubric

Score each dimension 1-5 (1=broken, 5=solid):

| Dimension | What to Evaluate |
|-----------|-----------------|
| **Completeness** | Do all documented stages, roles, and tools actually work? |
| **Enforcement** | Are rules enforced (tool-level) or just advised (prose)? |
| **Error Quality** | Are error messages clear, specific, and actionable? |
| **Consistency** | Do MCP tools, stage YAML, role specs, and docs agree with each other? |
| **Fail-Safety** | Does the system fail safe (block) or fail open (allow and log)? |
| **Idempotency** | Can operations be safely retried? |
| **Documentation** | Are valid values, required fields, and constraints documented? |
| **Role Isolation** | Do tool permissions actually prevent cross-role actions? |

## How to Work

1. **For each scenario**, create a new Change Set via MCP so findings are traceable.
2. **Run the test**, capturing exact tool calls, responses, errors, and behaviors.
3. **Record each finding** as evidence in the ledger (classification: RISK) with:
   - What you tried (exact tool call or action)
   - What happened (exact response or error)
   - What SHOULD have happened (expected behavior per docs)
   - Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
   - Category: one of [enforcement-gap, error-handling, documentation, consistency, data-integrity, role-boundary, missing-feature, regression]
4. **Do NOT fix anything.** You are the judge, not the developer.
5. **Do NOT skip a scenario** because it seems like it will work. Run it and prove it.

## Output

Write a single comprehensive report to `docs/adlc-runs/adlc-judge-report.md` with:

1. **Executive Summary** — overall health score (out of 40), top 3 critical findings
2. **Scenario Results** — for each scenario: what was tested, pass/fail per check, evidence IDs
3. **Findings Table** — all findings sorted by severity, with:
   - ID, Severity, Category, Scenario, Description, Expected vs Actual, Evidence ID
4. **Scoring Matrix** — the 8 dimensions scored with justification
5. **Recommendations** — prioritized list of fixes

Be ruthless. The goal is to find every crack before this ships to real teams.
```

---

## Usage Notes

- **Token budget:** This prompt drives ~50-80 MCP tool calls and takes 15-25 minutes.
- **Prerequisites:** The ADLC MCP server must be connected (`/mcp` to verify).
- **Variations:**
  - Add `Use worktree isolation for each agent role test` for deeper role-boundary testing.
  - Add `Also test resume: create a checkpoint, then try resuming from it` to test checkpointing.
  - Add `Run scenarios in parallel using forked agents` for speed (but harder to read output).
- **Prior findings from our test run (2026-10-07):**
  - `record_evidence` requires `model_id` for AGENT entries (undocumented)
  - `OBSERVATION` is not a valid classification (despite being commonly expected)
  - `record_transition` logs VIOLATION but doesn't block — fail-open design
  - Review agents (code-reviewer, security-reviewer) are read-only but prompts ask them to write files
  - Product-owner agent hit 10-turn limit before completing INTAKE
  - Stage gate requires `requirement_id` and `design_decision` outputs not produced by standard flow
