# ADR 0001 — Ship the MCP servers as one modular monolith

- **Status:** Accepted
- **Date:** 2026-10-03
- **Spec:** [plan v3.1 §6](../ai-sdlc-platform-plan-v3.1.md#6-mcp-server-design) ·
  design: [mcp-server-design.md](../../skills/mcp-servers/reference/mcp-server-design.md) ·
  code: [`skills/mcp-servers/adlc-mcp/`](../../skills/mcp-servers/adlc-mcp/README.md)

## Context

Plan §6 describes three stateful MCP servers — evidence-ledger (Phase 0), change-management
(Phase 2) and contract-registry (Phase 3) — and v3.1 adds a fourth engine, work-planning
(Phase 2). Built literally, that is four packages, four processes, four entries in every
client's MCP configuration, four credentials per role session, and four deployments to keep in
version lockstep — before a single pilot has shown which engines carry real load.

The engines are not independent. Change management needs the ledger's open blocking QUESTIONs
and unexpired ASSUMPTIONs to decide completion; work planning needs Change Set statuses to
derive story status. Separate servers would turn those into network calls and a distributed
consistency problem on day one.

At the same time, there are real reasons one engine may later need to stand alone: the ledger
becoming an org-wide remote service with its own auth (§4.3), a different team owning the
contract registry, or independent scaling. Whatever we build now must not make that expensive.

## Decision

Ship one package (`adlc-mcp`), one process, one MCP server named **`adlc`**, structured as a
**modular monolith**:

- Each engine is a module under `src/adlc_mcp/modules/<name>/` with `api.py` (the only public
  surface), `domain.py` (rules), `store.py` (persistence), `tools.py` (MCP registration) and
  `migrations/`.
- Each module owns **its own SQLite file** (`<module>.db`). No shared tables, no cross-module
  joins.
- **Modules never import each other.** A module that needs another declares a *port* (a
  Protocol) in its own `api.py`. The composition root `app.py` — the only file that knows more
  than one module — satisfies it with an in-process adapter around the other module's `api`.
- A small **shared kernel** (identity, errors, hashing, config, SQLite factory and migrations
  runner, the `Module` protocol, the MCP SDK shim) is the only code every module imports. It
  never imports a module.
- **Authorization lives inside each module** (not in `app.py`), so it survives extraction.
- `ADLC_MODULES` enables modules per phase; `python -m adlc_mcp --modules <name>` runs any one
  module alone.
- Tool names stay exactly as in §6 (role configs write them as `mcp:adlc.<tool>`).
- `tests/test_module_boundaries.py` enforces the import rules with an AST scan and proves that
  every module starts standalone with only its own database file.

## Extraction recipe

To move module `X` (say `evidence_ledger`) into its own server `adlc-X`:

1. **Copy the kernel.** Publish `adlc_mcp.kernel` as a tiny shared library (`adlc-kernel`), or
   vendor it. It has no dependency on any module, so it moves as-is.
2. **Move the module package.** Move `src/adlc_mcp/modules/X/` into the new package unchanged.
   Its imports are only `adlc_mcp.kernel.*` and its own files (the boundary test guarantees it).
3. **Give it a main.** Copy `__main__.py` and a one-module `app.py` that builds only `X`. The
   current monolith already does this with `--modules X`, so the behaviour is tested today.
4. **Move its data.** Copy `X.db` to the new deployment. No other module's data references it
   by key or join, so nothing else needs migrating.
5. **Write a remote adapter for each port that `X` satisfied.** For the ledger that is
   `EvidencePort` (used by change_management): implement `blocking_items` and
   `record_system_fact` as calls to the new server (MCP or HTTP), authenticated with a SYSTEM
   credential for the calling module.
6. **Swap the adapter in `app.py`.** Replace `LedgerEvidenceAdapter(ledger)` with the remote
   adapter and remove `X` from the monolith's `KNOWN_MODULES`. No other module changes, because
   they only ever saw the port.
7. **Register the new server with clients** under its own name (or keep `adlc` as a gateway).
   Tool names are unchanged, so role definitions that reference `mcp:adlc.<tool>` change only
   their server prefix, which the role generator emits.
8. **Replace pilot identity if needed.** An extracted, shared service is exactly the point where
   §4.3 says to move to OAuth2 / mTLS / RBAC: replace `kernel.identity.resolve_identity`.
9. **Run the module's own tests** in the new repo; delete them from the monolith; keep the
   boundary test for the remaining modules.

## Consequences

**Positive**
- One install, one process, one MCP entry, one credential per role session — the Phase 0 pilot
  stays as light as the plan intends.
- Cross-module calls are in-process and transactional per module, with no network failure modes
  until an extraction actually requires them.
- Extraction is a mechanical, rehearsed procedure: every module already runs standalone in CI.
- Missing ports fail safe (`NullEvidencePort`, `NullEvaluator`, `NullChangeSetStatus`), so a
  partially enabled phase never silently skips a check.

**Negative / costs**
- One process is one blast radius: a crash takes down every enabled module. Acceptable for a
  pilot; the per-module database files keep data blast radius separate.
- All modules share one release cadence and one credential surface until extracted.
- Because modules cannot join across databases, cross-module views (e.g. "story status" needing
  Change Set status) go through ports and are assembled in code — slightly more code than a SQL
  join, but that is precisely what keeps extraction cheap.
- The boundary rules hold only while the test does; it must stay in the required CI checks.

## Alternatives considered

- **Four separate servers now (plan §6 literally).** Rejected: pays the distribution cost before
  any evidence that it is needed, and forces a network contract between engines that are still
  changing.
- **One server with one shared database and free cross-module imports.** Rejected: cheapest
  today, but extraction later would mean untangling shared tables and imports — the costly
  rewrite this ADR exists to avoid.
