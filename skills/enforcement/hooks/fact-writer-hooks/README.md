# fact-writer-hooks (PostToolUse)

Writes `FACT` entries to the Evidence Ledger straight from tool results. Plan §4.3: FACT
entries are written by hooks — zero model tokens, and they can't be skipped because hooks run
regardless of what the model decides. The model only writes INFERENCE, ASSUMPTION, DECISION,
QUESTION, PROPOSAL, and RISK.

| Tool family | `source_type` | `source` | `content` |
|---|---|---|---|
| Read / view | `file_read` | file path | sha256 of content + truncated content |
| Bash / shell | `command_output` | `cmd: <command>` | command, truncated output, sha256 |
| Grep / Glob / search | `tool_output` | tool + args | truncated result |
| WebFetch / WebSearch | `external_fetch` | URL / query | sha256 + truncated body |
| `mcp__*` tools | `mcp_response` | tool name | truncated response |

File writes are not FACTs here — they're captured by git as diffs.

`source_type` → `trust_level` mapping is owned by the ledger (the caller never supplies a
trust level). Expected mapping: `file_read`/`tool_output` → REPOSITORY, `command_output`/
`hook_observation` → SYSTEM, `external_fetch`/`mcp_response` → EXTERNAL_UNSTRUCTURED.

## Ledger call
```
python skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py append-fact   < entry.json
```
with `ADLC_HOOK_NAME=fact-writer` in the environment. **Fails open**: errors go to
`.adlc/hook-errors.log` and the agent continues.
