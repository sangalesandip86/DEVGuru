# OWASP Top 10 for Agentic Applications — Coverage Map

Source taxonomy: OWASP Top 10 for Agentic Applications (ASI01–ASI10), OWASP GenAI Security Project.
Plan reference: §4.8 (`ai-agent-testing`), §3 tree annotations.

> Verify the category titles against the current OWASP publication before citing this table externally —
> category names can be revised between releases.

| ID | Category | Status | Covered by | Platform control under test |
|---|---|---|---|---|
| ASI01 | Agent Goal Hijack | **Covered** | [`policy-bypass-tests`](../policy-bypass-tests/SKILL.md), [`prompt-injection-tests`](../prompt-injection-tests/SKILL.md) | Binding skills loaded by policy; trust-boundaries; Rule of Two (§5.9) |
| ASI02 | Tool Misuse and Exploitation | **Covered** | [`tool-misuse-tests`](../tool-misuse-tests/SKILL.md) | Per-role tool scoping; operation classes (§4.5) |
| ASI03 | Identity and Privilege Abuse | **Covered** | [`agent-authorization-tests`](../agent-authorization-tests/SKILL.md) | Server-derived identity (§5.8); one credential per role; no APPROVED/INTEGRATED/RELEASED tool |
| ASI04 | Agentic Supply Chain Vulnerabilities | Deferred (Phase 2+) | — | Relevant once third-party skills/MCP servers are in use; signed skill supply chain is itself deferred (§2) |
| ASI05 | Unexpected Code Execution | Deferred (Phase 2+) | — | Partly mitigated today by sandboxing and control-file denial; dedicated tests deferred |
| ASI06 | Memory and Context Poisoning | Partial (adjacent) | [`prompt-injection-tests`](../prompt-injection-tests/SKILL.md) (content-origin cases) | Untrusted content entering context; ledger entries carry server-derived trust levels. Long-lived memory tests deferred |
| ASI07 | Insecure Inter-Agent Communication | Deferred (Phase 2+) | — | Typed handoffs with `repo@sha:path` + content hash; tests deferred until multi-agent parallel execution |
| ASI08 | Cascading Failures | Partial (adjacent) | [`prompt-injection-tests`](../prompt-injection-tests/SKILL.md) (injection propagating through a handoff) | Iteration caps, failure-class retry policy (§4.1). Full cascade tests deferred |
| ASI09 | Human-Agent Trust Exploitation | **Covered** | [`policy-bypass-tests`](../policy-bypass-tests/SKILL.md) | human-review-format; REVIEWED ≠ VERIFIED ≠ APPROVED (§5.5) |
| ASI10 | Rogue Agents | Deferred (Phase 2+) | — | Evidence Ledger audit trail; dedicated detection tests deferred |

## Notes on the plan's mapping
- The §3 tree annotates `prompt-injection-tests` as "ASI06/ASI08-adjacent", and §4.8 maps it to "the
  content-origin risks in the ASI catalog". Indirect prompt injection is also the main *mechanism* behind
  ASI01 goal hijack, so prompt-injection cases that aim to change the agent's objective are tagged ASI01 as
  well. Review whether to make that explicit in the plan.
- Deferral rationale (plan §4.8): these categories matter more once third-party skills, long-lived agent
  memory, and multi-agent parallel execution are in use — Phase 2+. Revisit this table at each phase gate.

## Test-case ID scheme
`AAT-<ASI id>-<nnn>`, e.g. `AAT-ASI02-004`. Every case lists: setup, attack input, expected platform behavior,
the enforcement point it exercises, and the evidence that proves the outcome.
