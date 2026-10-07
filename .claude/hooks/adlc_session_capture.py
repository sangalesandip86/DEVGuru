"""ADLC Session Capture — PostToolUse hook.

Records significant tool calls as journal events in the ADLC MCP server.
Zero LLM token cost — runs as a shell process outside the model.

Receives JSON on stdin from Claude Code:
  {"tool_name": "Edit", "tool_input": {...}, "tool_output": "..."}

Posts to http://127.0.0.1:<port>/api/capture when the ADLC server is running.
Silent no-op when the server is offline — never blocks the session.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.client import HTTPConnection

ADLC_PORT = int(os.environ.get("ADLC_PORT", "8181"))
ADLC_CHANGE_SET = os.environ.get("ADLC_CHANGE_SET", "")

CAPTURE_TOOLS = {"Edit", "Write", "Bash", "PowerShell", "NotebookEdit"}


def summarize(tool_name: str, tool_input: dict) -> dict:
    """Extract key info from a tool call — compact, no secrets."""
    payload: dict = {
        "tool": tool_name,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        # Strip absolute prefix for readability
        for prefix in ("C:/copies/git projects/DEVGuru/", "C:\\copies\\git projects\\DEVGuru\\"):
            fp = fp.replace(prefix, "")
        payload["file"] = fp
        payload["action"] = "edit" if tool_name == "Edit" else "write"
    elif tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        payload["command"] = cmd[:300] if len(cmd) > 300 else cmd
        payload["action"] = "execute"
    elif tool_name == "NotebookEdit":
        payload["action"] = "notebook_edit"
    return payload


def post_capture(payload: dict) -> None:
    """POST to ADLC server. Silent on failure."""
    try:
        body = json.dumps({
            "event_type": "session.tool_call",
            "payload": payload,
            "change_set_id": ADLC_CHANGE_SET,
            "run_id": "session-capture",
        }).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", ADLC_PORT, timeout=2)
        conn.request("POST", "/api/capture", body,
                     {"Content-Type": "application/json"})
        conn.getresponse().read()
        conn.close()
    except Exception:
        pass


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except (json.JSONDecodeError, EOFError, ValueError):
        return

    tool_name = data.get("tool_name", "")
    if tool_name not in CAPTURE_TOOLS:
        return

    tool_input = data.get("tool_input", {})
    payload = summarize(tool_name, tool_input)
    post_capture(payload)


if __name__ == "__main__":
    main()
