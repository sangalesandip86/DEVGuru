---
name: intent-router
description: Auto-classify user intent from natural language and route to the correct role and skill set. Users can always override with explicit skill invocation.
metadata:
  group: skill-routing
  phase: 0
  binding: true
  plan-ref: "§4 (addendum)"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Intent Router

## Purpose

Classify a user's free-text request into a structured intent and route it to the
correct ADLC role and skill combination — so users never need to memorize skill
names or commands. The user can always override by invoking a specific skill directly.

## When this applies

- At the start of every new user request that is not already addressed to a named
  skill or role.
- When a conversation shifts to a new task domain mid-session.

## Procedure

1. Read the user's request.
2. Match it against the intent taxonomy (see [intent-taxonomy.md](reference/intent-taxonomy.md)).
3. If confidence is HIGH (single clear match): announce the classification and
   proceed with the matched role + skills.
4. If confidence is MEDIUM (2–3 plausible matches): present the top options and
   let the user choose, defaulting to the most likely.
5. If confidence is LOW (ambiguous or novel): ask one clarifying question, then
   re-classify.
6. Pass the classified intent to the `skill-router` for technical skill binding.

## Override behavior

- If the user invokes a specific skill (`/skill-name`), skip classification and
  use it directly.
- If the user names a role explicitly ("as the architect, ..."), assign that role
  without classification.
- The classifier never overrides explicit user choices.

## Intent-to-role mapping

See the full taxonomy in [intent-taxonomy.md](reference/intent-taxonomy.md).
Quick reference:

| Intent Category | Primary Role | Secondary Roles |
|----------------|-------------|-----------------|
| Bug fix / debug | developer | qa-diagnose |
| New feature | product-owner → product-planner → developer | architect (if HIGH+) |
| Refactor | developer | architect (if cross-module) |
| Code review | code-reviewer | security-reviewer (if HIGH+) |
| Security audit | security-reviewer | — |
| Test writing | test-engineer | qa-derive (for design) |
| Architecture / design | architect | — |
| Requirements / planning | product-owner | product-planner |
| Explain / explore | (no role assignment) | (read-only skills) |
| Risk assessment | (risk-tiering skills) | — |
| Incident diagnosis | qa-diagnose | — |

## Enforcement

Guideline. The classifier is advisory — it suggests the best role/skill
combination but cannot enforce it. Users always retain the ability to override.

## Integration

- **Skill router:** intent classification feeds into Phase 1 coarse routing.
- **Context assembly:** classified intent determines Layer 2 (stage context).
- **Role quality rubrics:** the assigned role's rubric applies to the work.
