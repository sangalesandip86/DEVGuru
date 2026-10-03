# Preflight outcomes by artifact kind

`required` conditions come from [`stages.yaml`](../../stages.yaml):
- `always`
- `never` (optional)
- `tier>=MEDIUM`, `tier>=HIGH` (unknown tier = HIGH)
- `existing_repo` (the app repo already contains code)

A required input that is not required for this run reports `SATISFIED — not required`. An
optional input that is absent also reports SATISFIED.

| Kind | SATISFIED when | ADOPT when | BACKFILL when | ASK when | BLOCK when |
|---|---|---|---|---|---|
| `source-doc` | A source register lists ≥ 1 document | `--adopt source-doc=…` | — | Nothing supplied: ask where the documents are | — |
| `requirement` | REQ files exist and validate | `--adopt requirement=…` | No REQ files → INTAKE | — | A REQ file is invalid |
| `nfr-catalog` / `glossary` | The file exists and validates; every NFR has a target or an open question | — | Missing → INTAKE | — | Invalid, or an unquantified NFR has no question |
| `traceability-matrix` (INTAKE exit) | Every registered section has a row with the current hash | — | — | — | A section is missing, or its hash changed |
| `architecture-package` | README + service map present, architect REVIEWED/ACCEPT, and `human:tech-lead` APPROVAL at HIGH+ or for a superseding ADR | `--adopt architecture-package=…` (current state) | Missing → ARCHITECTURE | — | Present but missing the review or approval |
| `conventions-catalog` | Catalog present and fresh | — | Missing or stale → run `convention_scan.py` | App repo unresolved | — |
| `ready-story` | `readiness_gate` returns READY | `--adopt story=…` (tracker) | Missing → PLAN, or `INLINE_STORY` for LOW BUG_FIX/DOCUMENTATION | Several stories and no `--story` | NOT_READY: the missing DoR items are listed |
| `test-design` | The design's `ac_hash` equals the story's current hash, or a `.feature` file is tagged `@ST-n`, or characterization mode is on | — | Missing → DESIGN | No story or AC: characterization or backfill? | Stale: the AC changed after the freeze |
| `change-set` | The evidence export has a Change Set for the story (VERIFYING or later) | `--adopt change-set=PR` | Missing → IMPLEMENT | — | — |
| `test-suite` | Tests are present in the app repo | — | Missing → TEST | — | — |
| `review-verdict` | A REVIEWED/ACCEPT from code-reviewer or security-reviewer exists | — | Missing → REVIEW | — | — |
| `repo:<role>` | The resolver reports FOUND | — | — | AMBIGUOUS or MISSING (point to a path / init locally / request remote) | — |

The overall result is the worst outcome, ordered SATISFIED < ADOPT < BACKFILL < ASK < BLOCK.
Exit code `0` means every input is SATISFIED. Any other overall result exits `1`.
