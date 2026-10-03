# Completion Criteria

A Change Set may move to `INTEGRATED` only when **ALL** hold:

1. All required gates for its risk tier have passed (§5.4). A gate passes at the authority its
   type requires: deterministic checks at `VERIFIED`, judgment gates at `REVIEWED` (ACCEPT), human
   gates at `APPROVED`. A `REVIEWED` never substitutes for a required `VERIFIED`.
2. No `UNRESOLVED` dependencies remain (`../../dependency-discovery/SKILL.md`).
3. No unexpired `ASSUMPTION` with impact > `LOW` remains. (Expired high-impact assumptions block too —
   they must be confirmed as FACT or converted to an answered QUESTION.)
4. No `QUESTION` in state `OPEN` with `blocking: true` remains. QUESTIONs carry
   `OPEN` / `ANSWERED` / `EXPIRED` state; an open blocking question fails this gate the same way an
   unresolved dependency does.
5. All required roles for the tier have produced their handoff (`record_handoff`), or — in Degraded
   Mode — the named human standing in has.
6. All repositories in the Change Set have passing verification (CI `VERIFIED` per repo, at the
   pinned or a re-validated snapshot).

7. Every story in `story_refs[]` has a Definition of Done that is **evaluable** — the evidence each
   DoD item needs (ac-coverage, required REVIEWED/VERIFIED entries) can be produced from this Change
   Set and its siblings (v3.1 §4.12; `skills/product-planning/policies/dod-policy.yaml`). `INTEGRATED`
   does not make a story DONE — the story's `completion-gate` decides that after all linked Change Sets
   integrate.

Story linkage: in Phase 1 (forge-native) the link is an `Implements: ST-<n>` line in the PR body;
from Phase 2 it is the Change Set's `story_refs[]`.

Also required:
- No security-reviewer `REJECT` outstanding (only a human lifts it — `roles/reference/conflict-resolution.md`).
- Snapshot currency validated (`validate_snapshot_currency`) — stale snapshots re-verify first.
- For HIGH/CRITICAL: `APPROVED` sits on top of `VERIFIED` evidence, never on an agent's say-so (§5.5).

The adlc `change_management` module (plan's Server 2) checks these before applying a merge event's `INTEGRATED` transition; if a merge is observed
while criteria fail (e.g., an admin bypass), the server records the transition **and** a `RISK` entry.
