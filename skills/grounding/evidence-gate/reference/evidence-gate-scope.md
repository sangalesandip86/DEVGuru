# Evidence Gate — Scope

The evidence gate is valuable precisely because its guarantee is narrow and honest. Stating
it as broader than it is would make reviewers trust it for things it does not check.

## Guarantees
Every claim in the following artifacts traces to a source (file:line, command output, doc URL,
or user statement) — or is explicitly marked as a QUESTION or tagged ASSUMPTION:

| Artifact | Where defined |
|---|---|
| Handoff between roles | `roles/reference/handoff-schema.md` |
| DECISION entry | `core/evidence-ledger/reference/ledger-entry-schema.md` |
| RISK entry | same |
| QUESTION entry | same |
| Approval summary shown to a human | `grounding/human-review-format` |

## Does not guarantee

| Not guaranteed | Caught instead by |
|---|---|
| That every sentence of an agent's free-form reasoning is individually sourced | Not caught — out of scope by design |
| That the conclusion drawn from a source is correct | QA verification (`roles/qa-derive`, `roles/qa-diagnose`) |
| That code is well-designed or maintainable | Code review (`roles/code-reviewer`) |
| That the output addresses the real requirement | Human review (`grounding/human-review-format`, approval matrix) |
| That patterns of mistakes stop recurring | `/self-improvement` |

## Accepted source forms

| Form | Example | Notes |
|---|---|---|
| Pinned file reference | `repo-a@a1b2c3d:src/billing/fees.py:42` | Bare mutable filenames are not acceptable across a handoff |
| Ledger FACT reference | `ENTRY-9981` | Hook-written command output or file read |
| Doc URL | `https://… (retrieved 2026-10-03)` | Carries EXTERNAL_* trust |
| User statement | `ENTRY-1002 ("ship behind a flag")` | The statement must itself be recorded |

## Failure handling
An artifact failing the gate is a structurally invalid output: RETRY under the iteration cap
(`grounding/agent-failure-modes/reference/failure-catalog.md`).
