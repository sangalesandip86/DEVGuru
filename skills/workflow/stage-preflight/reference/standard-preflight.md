# Standard Preflight — shared reference

Every skill with a `## Preflight` section runs the same two checks before its Procedure.
This file is the single source of truth; each SKILL.md links here and lists only its deltas.

## Steps

1. **Resolve the workspace** — run
   [workspace-resolver](../../workspace-resolver/SKILL.md), or pass its JSON with `--workspace`.
2. **Run stage-preflight** —
   ```
   python skills/workflow/stage-preflight/scripts/stage_preflight.py \
       --start <STAGE> [--end <STAGE>] \
       [--story ST-n] [--tier T] [--story-type TYPE] \
       [--workspace ws.json | --cwd <dir>] [--plans <dir>] \
       [--evidence evidence.json] [--adopt KIND=REF …] [--format text]
   ```
   The evidence export is SYSTEM-produced (reviews, approvals, questions, change sets).
   Never hand-write it.
3. **Act on each input's outcome:**

   | Outcome | Meaning | Action |
   |---|---|---|
   | `SATISFIED` | Artifact exists and gate passed, or optional | Nothing |
   | `ADOPT` | Exists outside the platform; supplied with `--adopt` | [brownfield-adoption](../../brownfield-adoption/SKILL.md): import as DRAFT, then let the gate run |
   | `BACKFILL` | Missing | Run the named `backfill_stage` (smallest run), the conventions scan, or an inline story (LOW BUG_FIX/DOCUMENTATION only) |
   | `ASK` | Ambiguous, or a human must choose | One batched QUESTION with the listed `options` and a proposed default |
   | `BLOCK` | Exists but a gate failed on existing evidence | Report the `missing` items; do not proceed |

4. **Interpret the tier.** `effective_tier` = max(declared tier, story-type floor, path-based
   tier). Unknown → HIGH. Inputs marked `tier>=…` follow it. A user saying "it's small" never
   lowers the tier — record as ASSUMPTION.

## Cross-cutting skills

A skill with `stage: CROSS_CUTTING` has no stage inputs of its own and is loaded alongside
whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

## Brownfield

When the app repo already has code, ARCHITECTURE, DESIGN and IMPLEMENT require a **fresh**
conventions catalog (§4.15). Stale when: a declared standard's hash changed or the file was
removed; a dependency manifest is newer than the catalog; HEAD differs from a recorded
`head_sha`. Stale → BACKFILL: re-run `convention_scan.py` (cheap, no side effects).

## Characterization mode

Valid only at TEST, and only when the user chose it. Resulting tests never count as AC
verification.

## References

- [stage_preflight.py](../scripts/stage_preflight.py) · [outcomes.md](outcomes.md)
- [stages.yaml](../../stages.yaml) · [stages.schema.json](../../stages.schema.json)
