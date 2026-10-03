#!/usr/bin/env python3
"""ConfigChange-class hook: log every attempted control-file change, regardless of outcome.

Plan §4.1 / §4.11: any control-file write — allowed, denied, or attempted by a compromised
session — is logged. Portable mode registers this on PreToolUse (Copilot `preToolUse`)
alongside control-file-guard so *attempts* are captured even when the guard denies them.
Where Claude Code exposes a dedicated configuration-change event, register it there too;
any payload carrying a `file_path`/`source` is accepted. (Verify the current event name
against the Claude Code hook reference before relying on it — plan §8.)

Writes:
  * a JSONL line to .adlc/config-changes.log (always, local, cannot be skipped by the model)
  * a FACT entry to the Evidence Ledger via the ledger CLI (fails open)
Never blocks — blocking is control-file-guard's job.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import adlc_enforcement as ae  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "control-file-guard"))
from control_file_guard import shell_write_targets  # noqa: E402

HOOK_NAME = "config-change-logger"


def touched_control_files(event: ae.HookEvent, globs: list[str], repo_root: str) -> list[tuple[str, str]]:
    key = event.tool_key
    if key in ae.FILE_WRITE_TOOLS:
        paths = event.file_paths()
    elif key in ae.SHELL_TOOLS:
        paths = shell_write_targets(event.command())
    else:
        # Dedicated config-change events: accept any path-like field.
        paths = event.file_paths() + [str(event.raw[k]) for k in ("file_path", "source") if event.raw.get(k)]
    hits = []
    for p in paths:
        g = ae.match_control_path(p, globs, repo_root)
        if g:
            hits.append((p, g))
    return hits


def main() -> int:
    repo_root = os.getcwd()
    try:
        event = ae.parse_event(ae.read_stdin_json())
        repo_root = ae.repo_root_for(event)
        globs = ae.load_control_globs(os.environ.get("ADLC_CONTROL_PATHS"))
        for path, glob in touched_control_files(event, globs, repo_root):
            record = {
                "event": event.event or "unknown", "tool": event.tool_name, "path": path,
                "glob": glob, "platform": event.platform, "session_id": event.session_id,
                "risk_tier": "CRITICAL",
            }
            ae.log_line(repo_root, "config-changes.log", record)
            ae.append_fact({
                "run_id": event.session_id or "unknown-run",
                "tool": event.platform,
                "source_type": "hook_observation",
                "content": f"Control-file change attempted via {event.tool_name} on {path} "
                           f"(matches {glob}); CRITICAL tier, human approval required.",
                "source": f"hook:{HOOK_NAME}:{event.event or 'PreToolUse'}",
                **({"change_set_id": os.environ["ADLC_CHANGE_SET_ID"]} if os.environ.get("ADLC_CHANGE_SET_ID") else {}),
            }, repo_root, HOOK_NAME)
    except Exception as exc:  # noqa: BLE001 — logging hook never blocks
        ae.log_line(repo_root, "hook-errors.log", {"hook": HOOK_NAME, "error": str(exc)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
