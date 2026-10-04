#!/usr/bin/env python3
"""Fail-closed sanitization gate for anything leaving project scope (ADR 0006 §4).

Runs on incident notes, lessons and synthetic reproductions. Content passes only if ALL hold:
  1. no per-project blocklist term (build_blocklist.py output) appears, whole-word,
     case-insensitive;
  2. no PII or secret pattern matches — reusing
     skills/enforcement/ci-checks/test-integrity/fixture_pii_scan.py when present (every
     finding fails, including "warn" severity), plus a built-in secret/PII subset that always
     runs;
  3. no 8-word shingle is shared verbatim with any text file under the given project paths.
Fail-closed: a missing/unreadable blocklist, no --project-path, an unreadable input or any
internal error yields result FAIL.

Usage:  python sanitize_check.py INPUT [...] --blocklist blocklist.json --project-path DIR [...]
        (INPUT: .json — all string values are checked; anything else — checked as text;
         "-" reads stdin)
Output: {"result": "PASS"|"FAIL", "checked": [...], "findings": [...], "errors": [...]}
Exit:   0 PASS, 1 FAIL (findings), 2 FAIL (setup/internal error)
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PII_SCAN = REPO / "skills" / "enforcement" / "ci-checks" / "test-integrity" / "fixture_pii_scan.py"
SHINGLE = 8
MAX_FILE_BYTES = 2_000_000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".adlc"}
TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt",
                 ".go", ".rb", ".cs", ".swift", ".dart", ".sql", ".feature", ".xml", ".html", ".csv", ".toml",
                 ".cfg", ".ini", ".properties", ".sh", ".php", ".rs", ".scala", ".vue"}
RESERVED = ("example.com", "example.org", "example.net")

BUILTIN = [
    ("SECRET_LIKE", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SECRET_LIKE", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("SECRET_LIKE", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("SECRET_LIKE", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("SECRET_LIKE", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("SECRET_LIKE", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    ("SECRET_LIKE", re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[^\s'\"]{6,}")),
    ("SECRET_LIKE", re.compile(r"(?i)\b[a-z]+://[^\s:/]+:[^\s@/]+@")),
    ("SSN", re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])")),
]
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def _mask(v: str) -> str:
    return v[:2] + "…" + v[-2:] if len(v) > 6 else "…"


def load_pii_scanner():
    if not PII_SCAN.is_file():
        return None
    spec = importlib.util.spec_from_file_location("fixture_pii_scan", PII_SCAN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return getattr(mod, "scan_text", None)


def strings_of(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in strings_of(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings_of(v)]
    return []


def read_input(name: str) -> str:
    raw = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
    if name.endswith(".json"):
        return "\n".join(strings_of(json.loads(raw)))
    return raw


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(text: str) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def check_blocklist(text: str, terms: list[str]) -> list[dict]:
    out = []
    for term in terms:
        t = term.strip()
        if not t:
            continue
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.I)
        if pat.search(text):
            out.append({"check": "blocklist", "term": t})
    return out


def check_pii(text: str, scanner) -> list[dict]:
    out = []
    if scanner is not None:
        for f in scanner("<candidate>", text, set(), set()):
            out.append({"check": "pii", "type": f.get("type"), "severity": f.get("severity"),
                        "line": f.get("line"), "source": "fixture_pii_scan"})
    for kind, pat in BUILTIN:
        for m in pat.finditer(text):
            out.append({"check": "pii", "type": kind, "value_masked": _mask(m.group(0)), "source": "builtin"})
    if scanner is not None:  # it already covers e-mail and card numbers, with documented test-card exceptions
        return _dedupe(out)
    for m in EMAIL.finditer(text):
        dom = m.group(1).lower()
        if not (dom.endswith(RESERVED) or dom.endswith((".test", ".example", ".invalid", ".localhost"))):
            out.append({"check": "pii", "type": "EMAIL", "value_masked": _mask(m.group(0)), "source": "builtin"})
    for m in PAN.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits) and len(set(digits)) > 1:
            out.append({"check": "pii", "type": "PAN", "value_masked": _mask(digits), "source": "builtin"})
    return _dedupe(out)


def _dedupe(findings: list[dict]) -> list[dict]:
    seen, uniq = set(), []
    for f in findings:
        key = (f["type"], f.get("line"), f.get("value_masked"), f.get("source"))
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def project_files(paths: list[Path]):
    for base in paths:
        files = [base] if base.is_file() else base.rglob("*")
        for p in files:
            if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size <= MAX_FILE_BYTES:
                yield p


def check_overlap(text: str, paths: list[Path], exclude: set[Path]) -> list[dict]:
    cand = shingles(text)
    if not cand:
        return []
    out = []
    for p in project_files(paths):
        if p.resolve() in exclude:
            continue
        try:
            hit = cand & shingles(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if hit:
            out.append({"check": "verbatim_overlap", "file": p.as_posix(), "shared_shingles": len(hit),
                        "example": " ".join(sorted(hit)[0])})
    return out


def run(inputs: list[str], blocklist: Path | None, project_paths: list[Path]) -> dict:
    errors: list[str] = []
    terms: list[str] = []
    if blocklist is None:
        errors.append("no --blocklist given (fail-closed)")
    else:
        try:
            terms = json.loads(blocklist.read_text(encoding="utf-8"))["terms"]
            if not isinstance(terms, list):
                raise ValueError("terms is not a list")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"blocklist unreadable: {exc} (fail-closed)")
    if not project_paths:
        errors.append("no --project-path given; verbatim-overlap check cannot run (fail-closed)")
    missing = [p.as_posix() for p in project_paths if not p.exists()]
    if missing:
        errors.append(f"project path(s) not found: {missing} (fail-closed)")
    try:
        scanner = load_pii_scanner()
    except Exception as exc:  # noqa: BLE001 - fail closed on any import problem
        scanner = None
        errors.append(f"fixture_pii_scan.py failed to load: {exc} (fail-closed)")

    findings: list[dict] = []
    exclude = {Path(i).resolve() for i in inputs if i != "-"}
    for name in inputs:
        try:
            text = read_input(name)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read {name}: {exc}")
            continue
        for f in check_blocklist(text, terms) + check_pii(text, scanner) + (
                check_overlap(text, project_paths, exclude) if project_paths and not missing else []):
            findings.append({"input": name, **f})
    return {
        "result": "PASS" if not findings and not errors else "FAIL",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "checked": inputs,
        "pii_scanner": "fixture_pii_scan.py" if scanner else "builtin-only",
        "findings": findings,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--blocklist", type=Path)
    ap.add_argument("--project-path", type=Path, action="append", default=[])
    args = ap.parse_args(argv)
    try:
        result = run(args.inputs, args.blocklist, args.project_path)
    except Exception as exc:  # noqa: BLE001 - fail closed
        print(json.dumps({"result": "FAIL", "findings": [], "errors": [f"internal error: {exc}"]}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["result"] == "PASS":
        return 0
    return 2 if result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
