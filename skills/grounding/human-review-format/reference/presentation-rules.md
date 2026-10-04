
# Presentation Rules

1. **Decision first.** The first line states what is being decided and by whom. No preamble.
2. **One screen.** The summary fits on one screen; detail goes behind links to ledger entries.
3. **Authority is never blurred.** Always label `VERIFIED` (machine), `REVIEWED` (agent
   judgment), `APPROVED` (human). Never write "verified" in prose for something only reviewed.
4. **Every claim is sourced** (`grounding/evidence-gate`). Unsourced content appears only as a
   labeled QUESTION or ASSUMPTION.
5. **Surface what the human is actually accepting**: blocking QUESTIONs, ASSUMPTIONs with
   impact > LOW, any fail-safe default applied, any Degraded Mode substitution.
6. **Show disagreement, don't resolve it.** Cross-domain conflicts present both positions with
   their evidence; the agent does not recommend overriding a REJECT.
7. **Diffs over descriptions.** For code or control-file changes, link or embed the actual diff
   (truncated with a link if large); never only describe it.
8. **Name model families** of implementer and reviewers for HIGH/CRITICAL tiers so the reviewer
   can see that `roles/reference/reviewer-diversity.md` was satisfied.
9. **State what was not checked.** If a gate was skipped (lower tier) or a check could not run,
   say so explicitly.
10. **No persuasion.** No confidence adjectives ("clearly", "obviously safe"), no urgency
    framing. Neutral, factual, terse.
11. **Options with consequences.** Always include reject and request-more-evidence as options.
12. **Stable identifiers.** Reference Change Set, snapshot, entry ids, and `repo@sha` — never
    "the latest version" or "the file I changed".
