"""Shared helpers for ADLC enforcement hooks and CI checks.

Standard library only. Imported by hooks via a sys.path insert relative to this file, so it
must stay dependency-free and importable on Python 3.10+.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

ENFORCEMENT_DIR = Path(__file__).resolve().parent.parent          # skills/enforcement
PLATFORM_ROOT = ENFORCEMENT_DIR.parent.parent                       # repo root
DEFAULT_CONTROL_PATHS = (
    PLATFORM_ROOT / "skills" / "governance" / "default-permissions" / "reference" / "control-file-paths.json"
)
DEFAULT_LEDGER_CLI = PLATFORM_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "scripts" / "ledger_cli.py"


# --------------------------------------------------------------------------- globs

def glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translate a repo-relative glob to a regex.

    `**/` matches zero or more directories, a trailing `/**` matches everything below,
    `*` matches within one path segment, `?` one non-slash character.
    """
    i, out = 0, []
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def load_control_globs(path: Path | str | None = None) -> list[str]:
    data = json.loads(Path(path or DEFAULT_CONTROL_PATHS).read_text(encoding="utf-8"))
    globs: list[str] = []
    for patterns in data["categories"].values():
        for g in patterns:
            if g not in globs:
                globs.append(g)
    return globs


def _normalize(p: str) -> str:
    return p.replace("\\", "/").strip()


def to_repo_relative(path: str, repo_root: str | None) -> tuple[str, bool]:
    """Return (posix path, inside_repo). Relative paths are taken as repo-relative."""
    p = _normalize(path)
    if not p:
        return p, True
    is_abs = p.startswith("/") or bool(re.match(r"^[A-Za-z]:/", p)) or p.startswith("~")
    if not is_abs:
        while p.startswith("./"):
            p = p[2:]
        return str(PurePosixPath(p)) if p else "", True
    if repo_root:
        root = _normalize(os.path.abspath(repo_root)).rstrip("/")
        full = _normalize(os.path.abspath(os.path.expanduser(p)))
        if full.lower() == root.lower():
            return "", True
        if full.lower().startswith(root.lower() + "/"):
            return full[len(root) + 1:], True
    return _normalize(os.path.expanduser(p)), False


def match_control_path(path: str, globs: list[str], repo_root: str | None = None) -> str | None:
    """Return the first control glob the path matches, or None.

    Inside the repo only the repo-relative path is tested. Outside the repo every path
    suffix is tested, so `~/.claude/settings.json` still matches `.claude/**`.
    """
    rel, inside = to_repo_relative(path, repo_root)
    if not rel:
        return None
    candidates = [rel] if inside else ["/".join(rel.split("/")[i:]) for i in range(len(rel.split("/")))]
    compiled = [(g, glob_to_regex(g)) for g in globs]
    for cand in candidates:
        cand = cand.lstrip("/")
        for g, rx in compiled:
            if rx.match(cand):
                return g
    return None


# --------------------------------------------------------------------------- hook events

FILE_WRITE_TOOLS = {
    # Claude Code
    "edit", "write", "multiedit", "notebookedit",
    # GitHub Copilot (agent/CLI tool names)
    "create", "str_replace", "str_replace_editor", "insert", "apply_patch", "write_file", "edit_file",
}

# Dangerous paths blocked on ALL operations (read AND write)
DANGEROUS_PATH_PATTERNS = [
    r"(?:^|/)\.\.(?:/|$)",           # Parent directory traversal
    r"(?:^|/)~/.ssh(?:/|$)",         # SSH keys
    r"(?:^|/)\.env(?:\.|$)",         # .env files (.env, .env.local, etc.)
    r"(?:^|/)credentials\.(json|yaml|yml|toml)(?:$)",  # Credential files
    r"(?:^|/).*\.pem$",              # Certificate files
    r"(?:^|/).*\.key$",              # Private key files
    r"(?:^|/)\.git/config$",         # Git config (may contain credentials)
    r"(?:^|/)\.git/hooks/",          # Git hooks
    r"(?:^|/)\.netrc$",              # Netrc credentials
    r"(?:^|/)\.pgpass$",             # Postgres password file
]

FILE_READ_TOOLS = {
    "read", "cat", "head", "tail", "less", "more", "view",
    "get_content", "get-content",  # PowerShell
}

_DANGEROUS_RX = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATH_PATTERNS]


def match_dangerous_path(path: str) -> str | None:
    """Return the first dangerous pattern a path matches, or None."""
    normalized = _normalize(path)
    if not normalized:
        return None
    for rx, pattern in zip(_DANGEROUS_RX, DANGEROUS_PATH_PATTERNS):
        if rx.search(normalized):
            return pattern
    return None


SHELL_TOOLS = {"bash", "shell", "powershell", "run_in_terminal", "terminal"}
PATH_KEYS = ("file_path", "notebook_path", "path", "filePath", "filepath", "target_file")


@dataclass
class HookEvent:
    platform: str                    # "claude-code" | "copilot"
    event: str                       # PreToolUse / PostToolUse / ...
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str = ""
    session_id: str = ""
    cwd: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_key(self) -> str:
        return self.tool_name.lower()

    def file_paths(self) -> list[str]:
        paths = [str(self.tool_input[k]) for k in PATH_KEYS if self.tool_input.get(k)]
        for edit in self.tool_input.get("edits", []) or []:
            if isinstance(edit, dict):
                paths += [str(edit[k]) for k in PATH_KEYS if edit.get(k)]
        return paths

    def command(self) -> str:
        return str(self.tool_input.get("command") or self.tool_input.get("cmd") or "")


def parse_event(payload: dict[str, Any]) -> HookEvent:
    """Normalise Claude Code and GitHub Copilot hook stdin shapes."""
    if "tool_name" in payload or "hook_event_name" in payload:
        resp = payload.get("tool_response", "")
        return HookEvent(
            platform="claude-code",
            event=payload.get("hook_event_name", ""),
            tool_name=payload.get("tool_name", ""),
            tool_input=payload.get("tool_input") or {},
            tool_output=resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False),
            session_id=payload.get("session_id", ""),
            cwd=payload.get("cwd", ""),
            raw=payload,
        )
    args = payload.get("toolArgs", {})
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {"command": args}
    result = payload.get("toolResult") or {}
    output = result.get("textResultForLlm", "") if isinstance(result, dict) else str(result)
    return HookEvent(
        platform="copilot",
        event=payload.get("hookEventName", payload.get("event", "")),
        tool_name=payload.get("toolName", ""),
        tool_input=args if isinstance(args, dict) else {},
        tool_output=output,
        session_id=str(payload.get("sessionId", "")),
        cwd=payload.get("cwd", ""),
        raw=payload,
    )


def repo_root_for(event: HookEvent) -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or event.cwd or os.getcwd()


def read_stdin_json() -> dict[str, Any]:
    data = sys.stdin.read()
    return json.loads(data) if data.strip() else {}


# --------------------------------------------------------------------------- ledger + logs

def state_dir(repo_root: str) -> Path:
    d = Path(repo_root) / ".adlc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_line(repo_root: str, filename: str, record: dict[str, Any]) -> None:
    record = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), **record}
    try:
        with open(state_dir(repo_root) / filename, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def append_fact(entry: dict[str, Any], repo_root: str, hook_name: str) -> bool:
    """Pipe a FACT entry to the ledger CLI. Fails open: errors are logged, never raised."""
    cli = Path(os.environ.get("ADLC_LEDGER_CLI", DEFAULT_LEDGER_CLI))
    env = {**os.environ, "ADLC_HOOK_NAME": hook_name}
    try:
        if not cli.exists():
            raise FileNotFoundError(f"ledger CLI not found: {cli}")
        proc = subprocess.run(
            [sys.executable, str(cli), "append-fact"],
            input=json.dumps(entry, ensure_ascii=False),
            capture_output=True, text=True, timeout=10, env=env, cwd=repo_root or None,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ledger CLI exit {proc.returncode}: {proc.stderr.strip()[:500]}")
        return True
    except Exception as exc:  # noqa: BLE001 — fail open by design
        log_line(repo_root, "hook-errors.log", {"hook": hook_name, "error": str(exc), "entry": entry})
        return False
