# adlc-mcp

One deployable MCP server, named `adlc`, that hosts the platform's stateful engines as
modules of a **modular monolith** ([ADR 0001](../../../docs/adr/0001-mcp-modular-monolith.md),
design: [mcp-server-design.md](../reference/mcp-server-design.md)).

| Module | Plan | Phase | Tools |
|---|---|---|---|
| `evidence_ledger` | §6 Server 1 + ADR 0006 | 0 | `record_evidence` `query_evidence` `record_incident` `query_incidents` `record_correction` `record_lesson` `query_lessons` |
| `change_management` | §6 Server 2 | 2 | `create_change_set` `get_change_set` `update_status` `create_snapshot` `validate_snapshot_currency` `record_dependency` `compute_risk_tier` `record_handoff` `record_task` `checkpoint_task` `record_task_failure` · SYSTEM: `ingest_forge_event` · HUMAN: `override_risk_tier` |
| `work_planning` | v3.1 §6 Module 4 | 2 | `get_work_item` `query_work_graph` `evaluate_readiness` `evaluate_done` `link_change_set` · SYSTEM: `ingest_plan_commit` `ingest_work_event` |
| `contract_registry` | §6 Server 3 | 3 | `register_contract` `check_compatibility` `detect_drift` · SYSTEM: `record_deployment` |

Role tool lists refer to these as `mcp:adlc.<tool>`.

## Layout

```
adlc-mcp/
├── pyproject.toml            one package; optional extra [mcp]
├── scripts/
│   ├── ledger_cli.py         hook write path (append-fact / verify / query) — not an MCP tool
│   └── adlc_credentials.py   mint/inspect pilot credentials
├── src/adlc_mcp/
│   ├── kernel/               shared kernel: identity, errors, util, config, db, module protocol, mcp_compat
│   ├── modules/<name>/       api.py (only public surface) · domain.py · store.py · tools.py · migrations/
│   ├── app.py                composition root: enables modules, wires ports, one server
│   └── __main__.py           python -m adlc_mcp [--modules ...] [--list-tools]
└── tests/                    per-module tests + test_module_boundaries.py
```

## Run

```bash
pip install -e ".[mcp]"                     # or run from src/ with PYTHONPATH=src

# One credential per role session (pilot grade; only token hashes are stored)
python scripts/adlc_credentials.py issue --actor-type AGENT --actor-id agent:developer \
    --agent-role developer --tool claude-code --model-id <model>
# → {"token": "...", "stored_in": "~/.adlc/credentials.json"}

ADLC_TOKEN=<token> ADLC_MODULES=evidence_ledger python -m adlc_mcp            # stdio server
ADLC_TOKEN=<token> python -m adlc_mcp --modules change_management --list-tools  # one module alone
```

| Variable | Default | |
|---|---|---|
| `ADLC_TOKEN` | — | the role session's credential; identity is derived from it |
| `ADLC_CREDENTIALS` | `~/.adlc/credentials.json` | token-hash → identity map |
| `ADLC_MODULES` | `evidence_ledger` | Phase 0: `evidence_ledger`; Phase 2: `+change_management,work_planning`; Phase 3: `+contract_registry` |
| `ADLC_DATA_DIR` | `.adlc` | one SQLite file per module: `<module>.db` |
| `ADLC_LEDGER_DB` | — | override the ledger file |
| `ADLC_PLATFORM_RELEASE_SHA` | `unversioned` | recorded on every ledger entry |
| `ADLC_PATH_TIERS` | `skills/change-management/risk-tiering/path-tiers.json` | path → tier table |
| `ADLC_MAX_DIFF_LINES` | `400` | change-size cap (§7); above it `compute_risk_tier` returns `decompose_required` |
| `ADLC_HOOK_NAME` | `unknown` | `ledger_cli.py append-fact` identity: `hook:<name>` |
| `ADLC_EVIDENCE_RETENTION_DAYS` | `90` | local evidence payload retention (min 1); `ledger_cli.py purge` deletes older payloads |
| `ADLC_FAILURE_CLASS_MAP` | found under `skills/self-improvement/` | taxonomy that `failure_class` must belong to (format-only check if none exists) |
| `ADLC_REQUIRE_HOOK_TOKEN` / `ADLC_HOOK_TOKEN` | off | require a SYSTEM credential for `append-fact` |

### Example client configuration

`.mcp.json` is a **control file** (plan §4.1): it ships from managed settings, never edited by
an agent. One entry per role session, each with its own token:

```json
{
  "mcpServers": {
    "adlc": {
      "command": "python",
      "args": ["-m", "adlc_mcp"],
      "env": {
        "PYTHONPATH": "skills/mcp-servers/adlc-mcp/src",
        "ADLC_MODULES": "evidence_ledger",
        "ADLC_TOKEN": "${ADLC_DEVELOPER_TOKEN}"
      }
    }
  }
}
```

## Hooks → ledger

```bash
echo '{"run_id":"r1","tool":"claude-code","source_type":"command_output","content":"12 passed","source":"cmd:pytest"}' \
  | ADLC_HOOK_NAME=fact-writer python scripts/ledger_cli.py append-fact
python scripts/ledger_cli.py verify      # exit 1 if any hash chain or content commitment is broken
python scripts/ledger_cli.py purge       # daily: delete payloads past retention; chains stay valid
```

`source_type` → trust: `file_read`→REPOSITORY; `command_output`, `tool_output`, `hook_observation`→SYSTEM;
`external_fetch`→EXTERNAL_UNSTRUCTURED; `mcp_response`→EXTERNAL_STRUCTURED; anything unknown→EXTERNAL_UNSTRUCTURED.

## Self-improvement (ADR 0006)

Incidents are signals plus pointers (`skill`, `step`, `failure_class`, `signal_type`, `signal_source`,
`verification_strength`, `pattern_eligible`, `evidence_refs[]`, optional ≤280-char `note` from the
reviewer/human who caught the failure). Free-text use-case fields are rejected. Lessons need a
passing `sanitization_result`; only a human-approved lesson can be promoted to ORG scope, and never
by an agent. Evidence payloads are kept outside the hash chain behind a salted commitment, so
retention deletes content while `verify` stays green — see the design doc §4.

## Test

```bash
python -m unittest discover -s tests -t .     # stdlib only; no MCP SDK needed
```
