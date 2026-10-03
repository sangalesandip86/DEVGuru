# Remedy Selection, Size Budget, Pruning, and Sharing

From [ADR 0006](../../../../docs/adr/0006-self-improvement-lessons.md) §5–6.

## 1. Choose the remedy by what can be checked

| `remedy_kind` | When | Where it lands | Process |
|---|---|---|---|
| `GATE` | The lesson's `check` is mechanical and should block a state transition | DoR/DoD policy item (`skills/product-planning/policies/*.yaml`), CI gate | Enforcement change → control-file process, CRITICAL tier, human approval |
| `LINT` | Mechanical `check` that should flag rather than block, or runs at authoring time | `plan_lint.py`, test-integrity rules, hook | Same as GATE |
| `SKILL_TEXT` | Needs judgment; no mechanical check exists | A specific SKILL.md section or reference file | Control-file process |
| `EXAMPLE` | Judgment failure best fixed by showing one worked case | A reference file or example section | Control-file process |

- **Prefer GATE/LINT whenever `check` is mechanical.** A gate changes what the agent *can* do;
  prose only changes what it is told. `lesson_lint.py` warns when a mechanical `check` comes
  with a SKILL_TEXT/EXAMPLE remedy and no `remedy_target.rationale`.
- A new gate or lint must add its finding IDs to `failure-capture/reference/failure-class-map.json`,
  so its future catches cluster back to the same lesson.

## 2. Skill size budget
- Every SKILL.md has a budget: **body ≤ 500 lines** (default). Detail goes in `reference/` files
  that are loaded on demand.
- A SKILL_TEXT or EXAMPLE remedy must state `remedy_target.location` **and**
  `remedy_target.replaces_or_merges`: the existing text it replaces or merges into.
  Appending a new paragraph is the last resort, and only if the body stays within budget.
- If a revision would exceed the budget, merge it with or replace the weakest existing guidance
  (the guidance with the fewest firing lessons), or move detail into a reference file.

## 3. Prune remedies that don't fire
- Each lesson records `last_fired`: the date of the newest incident in its cluster. The remedy
  "fires" when its gate or lint catches something, or when a new incident joins the cluster.
- A remedy with **no matching incidents for 6 months** is put up for removal at the next review
  (`lesson_lint.py` flags `PRUNE_CANDIDATE`). Removal follows the same REVIEWED → APPROVED path.
  The reproduction stays as a regression eval unless the human retires it too.
- Retired lessons get `status: RETIRED` and are never deleted (audit).

## 4. Sharing scopes

| Scope | Default | Contents | Condition |
|---|---|---|---|
| `PROJECT` | always | Incidents, local evidence, draft lessons | — |
| `ORG` | on | Lessons, synthetic reproductions, skill revisions | `sanitize_check.py` PASS **and** human `APPROVED` (`approved_by: human:<role>`) |
| Cross-organization | **deferred** | Not built. It needs the signed skill supply chain that v3 already defers | — |

`occurrences.projects` counts how many projects contributed to a lesson. Each project's
contribution is merged at ORG level only from approved lessons, never from raw incidents.
