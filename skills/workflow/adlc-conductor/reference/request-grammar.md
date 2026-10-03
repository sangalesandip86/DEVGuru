# Request grammar

How `/adlc` turns what a user says into a ranged run. Stage names are case-insensitive, and the
synonyms below are accepted. When a request is ambiguous, the conductor raises one QUESTION with
a proposed default. It never guesses silently.

## Stage synonyms
| Stage | Also accepted |
|---|---|
| INTAKE | ingest, requirements, discovery, analyse docs |
| ARCHITECTURE | architecture, solution design, HLD, system design |
| PLAN | planning, backlog, epics, stories, decomposition, refinement |
| DESIGN | detailed design, LLD, test design, story design |
| IMPLEMENT | build, code, develop, implement, fix |
| TEST | tests, test automation, QA, characterization |
| REVIEW | review, code review, security review |
| INTEGRATE | merge, PR merged |
| RELEASE | deploy, ship, release |
| LEARN | retro, production feedback, incident |

## Forms
| Request | start | end | Notes |
|---|---|---|---|
| "from X to Y", "X through Y", "X → Y" | X | Y | Error if Y comes before X |
| "only X", "just X" | X | X | |
| "X" (a single stage verb) | X | X | |
| "resume", "continue", "resume from X" | checkpoint `stopped_at` (or X) | checkpoint `requested.end` (or X) | Reads `.adlc/runs/*/checkpoint.json` |
| "ingest these docs and go through architecture and planning" | INTAKE | PLAN | `--adopt source-doc=<paths>` |
| "implement ST-40" | IMPLEMENT | REVIEW (default) | Default end: REVIEW, because a PR ready for merge is the natural stop |
| "write tests for <legacy code>" | TEST | TEST | If no story or AC exists, preflight ASKs: characterization or backfill |
| "fix <bug>" (small, LOW) | IMPLEMENT | REVIEW | Inline-story mode when the tier is LOW and the type is BUG_FIX |
| "to production", "ship it" | … | RELEASE | Stops at INTEGRATE/RELEASE as observed events |

## Extracted parameters
- `story`: an `ST-n` mentioned in the request, or the only story in scope.
- `tier`: only from evidence (path tier, story type floor, `compute_risk_tier`). A user's
  "it's small" is recorded as an ASSUMPTION, never as the tier.
- `mode`: `characterization` only when the user accepts it at TEST.
- `adopt[]`: anything the user hands over that lives outside the platform:
  - documents → `source-doc`
  - a tracker export → `story` / `requirement`
  - existing architecture documents → `architecture-package`
  - an existing PR → `change-set`
