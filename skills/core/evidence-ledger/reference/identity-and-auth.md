# Identity and Authentication

## Rules
1. `agent_role`, `actor_id`, and `trust_level` are **derived server-side from the authenticated
   connection** — never accepted as caller-supplied parameters. A caller claiming to be
   `qa-derive` must actually be authenticated with that role's credential; nothing is taken on
   self-report. A request that includes any of these fields is rejected, not silently ignored,
   so misconfigured clients are noticed.
2. **One credential per role.** The MCP tool surface exposed to a credential contains only
   role-appropriate tools. There is no tool through which an agent-authenticated caller can
   write an `APPROVED`, `INTEGRATED`, or `RELEASED` status, or a `VERIFIED` lifecycle state.
3. **FACT entries are written by hooks directly** — zero model tokens, and they cannot be
   skipped because hooks run regardless of what the model decides. The model only ever writes
   INFERENCE, ASSUMPTION, DECISION, QUESTION, PROPOSAL, and RISK entries. Hooks authenticate as
   SYSTEM (`actor_id: hook:<hook-name>`).
4. **Hash-chained entries** make tampering detectable even on a local file.
5. **Deployment scope:** a per-workspace SQLite database is acceptable for a true single-user,
   single-workspace pilot only. Once more than one person, or any cloud-hosted agent session,
   is involved, move to a remote authenticated MCP service, reusing whatever OAuth2/mTLS/RBAC
   layer the rest of the platform's integrations already use rather than designing a new one.

## Credential → identity mapping

| Credential | `actor_type` | `actor_id` | `agent_role` | Tools exposed (evidence_ledger module) |
|---|---|---|---|---|
| Role token `role:developer` (etc.) | AGENT | `agent:<role>:<session>` | `<role>` | `record_evidence` (non-FACT), `query_evidence`, `record_correction`, `record_incident` (signal + pointers only), `query_incidents` (pointers, not content), `record_lesson` (reviewing roles; ORG scope only after human APPROVED) |
| Hook token `hook:<name>` | SYSTEM | `hook:<name>` | — | `append-fact` (CLI / internal), no query |
| CI / forge webhook | SYSTEM | `ci:<pipeline>` / `forge:<provider>` | — | Ingest machine evidence → may set `VERIFIED`; ingest human review events → `APPROVED` |
| Authenticated human (OAuth/SSO) | HUMAN | `human:<user-id>` (+ approver role, e.g. `human:tech-lead`) | — | Approval actions via forge events, queries |

## Pilot mode (single user, local SQLite)
- Role tokens are random secrets in the managed (org) settings directory, one per role, mapped
  in a server-side file the agent cannot read or write (it is a control file).
- The MCP client config for each subagent passes its own token via env var; the server maps
  token → role. The agent never sees another role's token.
- The ledger file itself is outside the agent-writable workspace or is append-guarded; even
  so, the hash chain is the tamper-evidence of last resort.

## What this does not protect against
A fully compromised host with write access to the database and the server's token map can
rewrite history consistently. That is the reason for the move to a remote service as soon as
more than one person is involved.
