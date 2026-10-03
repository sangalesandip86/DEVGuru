#!/usr/bin/env python3
"""PostToolUse hook: write FACT entries to the Evidence Ledger from tool results.

Plan §4.3 identity-and-auth: FACT-classified entries (command output, file reads) are written
by hooks directly — zero model tokens, and they cannot be skipped because hooks run
regardless of what the model decides. The model never self-reports a FACT.

Contract (docs/authoring-conventions.md): one JSON object on stdin of
`ledger_cli.py append-fact`: {run_id, tool, source_type, content, source, change_set_id?}.
Identity is actor_type=SYSTEM, actor_id=hook:fact-writer (passed via ADLC_HOOK_NAME); trust
level is derived by the ledger from source_type.

Fails OPEN: a ledger write error is logged to .adlc/hook-errors.log and never blocks the
agent — losing one FACT is preferable to halting all work, and the gap is visible in the log.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import adlc_enforcement as ae  # noqa: E402

HOOK_NAME = "fact-writer"
MAX_CONTENT = int(os.environ.get("ADLC_FACT_MAX_CHARS", "4000"))

READ_TOOLS = {"read", "view", "read_file", "notebookread"}
SEARCH_TOOLS = {"grep", "glob", "search", "file_search", "grep_search"}
FETCH_TOOLS = {"webfetch", "fetch", "web_fetch", "websearch"}


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _truncate(text: str) -> str:
    if len(text) <= MAX_CONTENT:
        return text
    return text[:MAX_CONTENT] + f"\n…[truncated {len(text) - MAX_CONTENT} chars]"


def build_entry(event: ae.HookEvent) -> dict | None:
    key = event.tool_key
    out = event.tool_output or ""
    if key in READ_TOOLS:
        paths = event.file_paths()
        source = paths[0] if paths else "unknown-file"
        source_type, content = "file_read", f"Read {source} ({_digest(out)})\n{_truncate(out)}"
    elif key in ae.SHELL_TOOLS:
        cmd = event.command()
        source = f"cmd: {cmd[:300]}"
        source_type, content = "command_output", f"$ {cmd}\n{_truncate(out)}\n[{_digest(out)}]"
    elif key in SEARCH_TOOLS:
        source = f"{event.tool_name}: {str(event.tool_input)[:300]}"
        source_type, content = "tool_output", _truncate(out)
    elif key in FETCH_TOOLS:
        url = str(event.tool_input.get("url") or event.tool_input.get("query") or "")
        source = url or event.tool_name
        source_type, content = "external_fetch", f"{_digest(out)}\n{_truncate(out)}"
    elif key.startswith("mcp__") or key.startswith("mcp_"):
        source = event.tool_name
        source_type, content = "mcp_response", _truncate(out)
    else:
        return None  # writes are captured as git diffs, not FACTs
    entry = {
        "run_id": event.session_id or os.environ.get("ADLC_RUN_ID", "unknown-run"),
        "tool": event.platform,
        "source_type": source_type,
        "content": content,
        "source": source,
    }
    if os.environ.get("ADLC_CHANGE_SET_ID"):
        entry["change_set_id"] = os.environ["ADLC_CHANGE_SET_ID"]
    return entry


def main() -> int:
    repo_root = os.getcwd()
    try:
        event = ae.parse_event(ae.read_stdin_json())
        repo_root = ae.repo_root_for(event)
        entry = build_entry(event)
        if entry:
            ae.append_fact(entry, repo_root, HOOK_NAME)
    except Exception as exc:  # noqa: BLE001 — fail open
        ae.log_line(repo_root, "hook-errors.log", {"hook": HOOK_NAME, "error": str(exc)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
