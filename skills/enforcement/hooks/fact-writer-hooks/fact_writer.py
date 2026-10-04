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
import re
import sys
from pathlib import Path

_skills_root_env = os.environ.get("ADLC_SKILLS_ROOT")
_enforcement = Path(_skills_root_env, "skills", "enforcement").resolve() if _skills_root_env else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_enforcement / "lib"))
import adlc_enforcement as ae  # noqa: E402

HOOK_NAME = "fact-writer"
MAX_CONTENT = int(os.environ.get("ADLC_FACT_MAX_CHARS", "4000"))

READ_TOOLS = {"read", "view", "read_file", "notebookread"}
SEARCH_TOOLS = {"grep", "glob", "search", "file_search", "grep_search"}
FETCH_TOOLS = {"webfetch", "fetch", "web_fetch", "websearch"}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential|auth)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(aws|azure|gcp|github|gitlab|slack|stripe|twilio)[_-]?(secret|key|token)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[bpors]-[A-Za-z0-9\-]+"),
]

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(?i)\.env(\.|$)"),
    re.compile(r"(?i)(credentials|secrets|tokens|passwords)\.(json|yaml|yml|toml|ini|cfg|conf)$"),
    re.compile(r"(?i)(id_rsa|id_ed25519|id_ecdsa)(\.pub)?$"),
    re.compile(r"(?i)\.(pem|key|p12|pfx|jks)$"),
]


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _truncate(text: str) -> str:
    if len(text) <= MAX_CONTENT:
        return text
    return text[:MAX_CONTENT] + f"\n…[truncated {len(text) - MAX_CONTENT} chars]"


def _is_sensitive_path(path: str) -> bool:
    return any(p.search(path) for p in SENSITIVE_FILE_PATTERNS)


def _redact_content(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def build_entry(event: ae.HookEvent) -> dict | None:
    key = event.tool_key
    out = event.tool_output or ""
    source_path = None
    if key in READ_TOOLS:
        paths = event.file_paths()
        source = paths[0] if paths else "unknown-file"
        source_path = source
        digest = _digest(out)
        if _is_sensitive_path(source):
            source_type = "file_read"
            content = f"Read {source} ({digest}) [{len(out)} bytes] [sensitive file: content redacted]"
        else:
            first_line = out.split("\n")[0][:200] if out else ""
            source_type = "file_read"
            content = f"Read {source} ({digest}) [{len(out)} bytes]\nFirst line: {first_line}"
    elif key in ae.SHELL_TOOLS:
        cmd = event.command()
        source = f"cmd: {cmd[:300]}"
        redacted = _redact_content(_truncate(out))
        source_type, content = "command_output", f"$ {cmd}\n{redacted}\n[{_digest(out)}]"
    elif key in SEARCH_TOOLS:
        source = f"{event.tool_name}: {str(event.tool_input)[:300]}"
        source_type, content = "tool_output", _redact_content(_truncate(out))
    elif key in FETCH_TOOLS:
        url = str(event.tool_input.get("url") or event.tool_input.get("query") or "")
        source = url or event.tool_name
        source_type, content = "external_fetch", f"{_digest(out)}\n{_redact_content(_truncate(out))}"
    elif key.startswith("mcp__") or key.startswith("mcp_"):
        source = event.tool_name
        source_type, content = "mcp_response", _redact_content(_truncate(out))
    else:
        return None
    entry = {
        "run_id": event.session_id or os.environ.get("ADLC_RUN_ID", "unknown-run"),
        "tool": event.platform,
        "source_type": source_type,
        "content": content,
        "source": source,
    }
    if source_path:
        entry["source_path"] = source_path
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
