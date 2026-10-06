#!/usr/bin/env python3
"""PreToolUse hook: deny agent writes to platform control files (plan §4.1, §4.11).

Second layer behind managed-settings `permissions.deny`. Reads the canonical glob list from
skills/governance/default-permissions/reference/control-file-paths.json (override with
ADLC_CONTROL_PATHS).

Works for both Claude Code (`tool_name`/`tool_input`) and GitHub Copilot
(`toolName`/`toolArgs`) stdin shapes. On deny it prints the platform's
`permissionDecision: deny` JSON and exits 0; on an internal error it fails CLOSED with
exit 2, because a guard that fails open is not a guard.

Shell-command detection is heuristic ("obvious" writes only) — paraphrased shell writes are
caught by the managed-settings layer and CODEOWNERS review, not by this hook.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

_skills_root_env = os.environ.get("ADLC_SKILLS_ROOT")
_enforcement = Path(_skills_root_env, "skills", "enforcement").resolve() if _skills_root_env else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_enforcement / "lib"))
import adlc_enforcement as ae  # noqa: E402

HOOK_NAME = "control-file-guard"

# Commands / cmdlets that write, move, or delete files.
WRITE_VERBS = {
    "cp", "mv", "rm", "rmdir", "touch", "tee", "ln", "install", "truncate", "dd", "chmod", "chown",
    "mkdir", "rsync", "unlink", "patch",
    "set-content", "add-content", "out-file", "new-item", "remove-item", "copy-item",
    "move-item", "rename-item", "clear-content", "del", "copy", "move", "ren", "erase",
}
IN_PLACE_FLAGS = re.compile(r"(^|\s)(sed|perl|ruby)\s+(-[a-zA-Z]*i|--in-place)")
GIT_WRITE = re.compile(r"\bgit\s+(checkout|restore|apply|am|rm|mv)\b")
SCRIPT_WRITE = re.compile(r"(open\([^)]*['\"][wa]|write_text|writeFile|WriteAllText)")


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


REDIRECT_TARGET = re.compile(r"(?<![0-9&])>>?\s*['\"]?([^\s;&|'\"]+)|\btee\s+(?:-\S+\s+)*['\"]?([^\s;&|'\"]+)")


def shell_write_targets(command: str) -> list[str]:
    """Return candidate paths in a shell command that looks like it writes files.

    Redirections contribute only their target (so `cat AGENTS.md > out.txt` is allowed);
    write verbs, in-place editors, git restores and inline scripts contribute every argument.
    """
    if not command.strip():
        return []
    candidates = [a or b for a, b in REDIRECT_TARGET.findall(command)]
    toks = _tokens(command)
    verb_write = (
        any(t.lower() in WRITE_VERBS for t in toks)
        or bool(IN_PLACE_FLAGS.search(command))
        or bool(GIT_WRITE.search(command))
        or bool(SCRIPT_WRITE.search(command))
    )
    if verb_write:
        for tok in toks:
            for piece in re.split(r"[;&|><]+|^of=|=", tok):
                piece = piece.strip("'\"()")
                if piece and not piece.startswith("-"):
                    candidates.append(piece)
        # Paths embedded in quoted script bodies (python -c "open('x','w')")
        candidates += re.findall(r"['\"]([^'\"\s,()]+)['\"]", command)
    return [c for c in candidates if c]


READ_VERBS = {
    "cat", "head", "tail", "less", "more", "view", "type", "bat", "nl", "tac", "strings", "xxd",
    "od", "grep", "egrep", "rg", "cp", "scp", "source", ".",
    "get-content", "gc", "select-string",
}


def _extract_read_targets(command: str) -> list[str]:
    """Return candidate paths from a shell command that reads files (cat, head, ...).

    Heuristic: when any token is a read verb, every non-flag token (and redirect-input
    target) is a candidate. Over-matching is acceptable for a deny guard.
    """
    if not command.strip():
        return []
    toks = _tokens(command)
    out: list[str] = [m for m in re.findall(r"<\s*['\"]?([^\s;&|'\"<>]+)", command)]
    if any(t.lower() in READ_VERBS for t in toks):
        for tok in toks:
            for piece in re.split(r"[;&|><]+", tok):
                piece = piece.strip("'\"()")
                if piece and not piece.startswith("-"):
                    out.append(piece)
    return out


def evaluate(event: ae.HookEvent, globs: list[str], repo_root: str) -> tuple[str, str] | None:
    """Return (path, glob) of the first control-file write or dangerous-path access, or None.

    Dangerous-path hits are returned with glob = "DANGEROUS:<pattern>".
    """
    key = event.tool_key
    paths: list[str] = []
    if key in ae.FILE_WRITE_TOOLS:
        paths = event.file_paths()
    elif key in ae.SHELL_TOOLS:
        paths = shell_write_targets(event.command())
    for p in paths:
        g = ae.match_control_path(p, globs, repo_root)
        if g:
            return p, g

    # Dangerous paths are denied on ALL operations, including reads.
    all_paths = list(paths)
    if key in ae.FILE_READ_TOOLS:
        all_paths += event.file_paths()
    if key in ae.SHELL_TOOLS:
        all_paths += _extract_read_targets(event.command())
    for p in all_paths:
        dangerous = ae.match_dangerous_path(p)
        if dangerous:
            return p, f"DANGEROUS:{dangerous}"
    return None


def deny_payload(event: ae.HookEvent, reason: str) -> dict:
    if event.platform == "copilot":
        return {"permissionDecision": "deny", "permissionDecisionReason": reason}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    try:
        event = ae.parse_event(ae.read_stdin_json())
        repo_root = ae.repo_root_for(event)
        globs = ae.load_control_globs(os.environ.get("ADLC_CONTROL_PATHS"))
        hit = evaluate(event, globs, repo_root)
    except Exception as exc:  # noqa: BLE001 — fail closed
        print(f"[{HOOK_NAME}] internal error, failing closed: {exc}", file=sys.stderr)
        return 2
    if hit is None:
        return 0
    path, glob = hit
    if glob.startswith("DANGEROUS:"):
        reason = (
            f"Blocked by {HOOK_NAME}: '{path}' is a dangerous path (matches "
            f"'{glob[len('DANGEROUS:'):]}'): path traversal, secrets or credential material. "
            "Reads and writes of these paths are denied; ask a human if access is required."
        )
    else:
        reason = (
            f"Blocked by {HOOK_NAME}: '{path}' is a platform control file (matches '{glob}'). "
            "Control-file writes are CRITICAL tier and require human approval via a "
            "CODEOWNERS-reviewed PR; agents may not write them. Record a PROPOSAL instead."
        )
    ae.log_line(repo_root, "control-file-guard.log", {
        "decision": "deny", "tool": event.tool_name, "path": path, "glob": glob,
        "platform": event.platform, "session_id": event.session_id,
    })
    print(json.dumps(deny_payload(event, reason)))
    print(reason, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
