# Refinement protocol (three amigos)

| Amigo | Role | Sees | Contributes | Records |
|---|---|---|---|---|
| Business | `product-planner`, with `human:product-owner` for intent | requirement, plans/, repos (read) | value, scope, AC wording, splits | story PR; QUESTIONs |
| Test | `qa-derive` | **the story only** (implementation paths denied) | testability, missing negative paths, test outline | `REVIEWED` `qa_testability` + `ac_hash` |
| Build | `developer` | the snapshot of the affected repos | feasibility, hidden dependencies, size | `REVIEWED` `developer_feasibility` + `ac_hash` |

The three roles should run in **separate sessions with separate credentials**. Their
independence is the point: if one session plays all three amigos, it produces three opinions
from one mind.

## Loop

```
gate dry-run ─► MISSING items ─► planner fixes structural gaps ─┐
     ▲                                                          ▼
     │                         qa-derive: outline or QUESTIONs (blind)
     │                         developer: ACCEPT / REJECT + size
     │                         architect / security-reviewer if required
     └──── new AC hash? old reviews are stale, so re-run the affected reviews ◄┘
```

1. **Start from evidence.** Run `readiness_gate.py` (or read the last CI run). Only the MISSING, FAIL and REJECTED items are on the agenda.
2. **Planner pass.** Close the structural gaps from sources. Anything that can't be sourced becomes a QUESTION (blocking or not) or an expiring ASSUMPTION. Never invent a value to make the gate pass.
3. **qa-derive pass.** For each criterion, write at least one test idea, and for each functional criterion ask "what is the negative path?". Then:
   - If a criterion can't be tested from its text, ask a QUESTION that quotes it.
   - If all criteria are testable, ACCEPT. The outline is stored and becomes the frozen Pass 1 input.
4. **developer pass.** Check `affected_paths` against the code (run the dependency-discovery scanners). Look for hidden dependencies (UNRESOLVED until confirmed) and predict the diff size.
   - ACCEPT with the size, or REJECT with evidence: infeasible, wrong paths or unsafe.
   - A REJECT goes back to the planner, which gets one revision attempt before the disagreement escalates to a human (conflict-resolution rule 3).
5. **Specialists** per the DoR policy: architect for `API_CONTRACT` or `touches.api_contracts`, security-reviewer for `SECURITY_STORY` or RESTRICTED data. A specialist REJECT blocks within its domain, and only a human lifts it.
6. **Approval.** HIGH and CRITICAL stories need `human:product-owner` scope approval. Present it in [human-review-format](../../../grounding/human-review-format/SKILL.md): story, effective tier and why, the evidence summary, and open risks.

## Rules
- **AC edits re-open reviews.** Every change to the criteria changes the AC hash, and reviews pinned to the old hash stop counting. Batch your AC edits.
- **Max 3 cycles** between any two roles, then escalate to a human with both positions and the evidence.
- **No "ACCEPT with conditions".** A condition is either a criterion (add it) or a QUESTION (raise it).
- **Time-box refinement.** If a story needs more than two refinement rounds because the domain is unknown, convert the uncertainty into a SPIKE.

## Anti-patterns
| Anti-pattern | Why it's harmful |
|---|---|
| qa-derive reads the implementation "to be helpful" | It destroys the independence the platform relies on. The tool permission denies this; don't try to work around it. |
| Developer ACCEPTs without checking `affected_paths` | The path tier and the scope check then rest on a guess |
| Splitting by layer (API story, DB story, UI story) | None of the pieces delivers value on its own. Use the [slicing patterns](../../epic-decomposer/reference/slicing-patterns.md). |
| Turning every QUESTION into an ASSUMPTION to reach READY | ASSUMPTIONs with impact above LOW block READY anyway, and the DoR escape rate (plan §7) will show it |
