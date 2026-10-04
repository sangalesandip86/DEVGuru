#!/usr/bin/env python3
"""CI check: fail if tool-compatibility.md's verification date is stale.

Usage:
    python check_spec_currency.py                       # default 90-day threshold
    python check_spec_currency.py --max-age-days 60     # custom threshold
    python check_spec_currency.py --today 2027-01-15    # override date (testing)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DOC = REPO_ROOT / "docs" / "tool-compatibility.md"
DATE_RE = re.compile(r"[Vv]erified\b.*?(\d{4}-\d{2}-\d{2})")
DEFAULT_MAX_AGE = 90


def find_verified_date(text: str) -> date | None:
    m = DATE_RE.search(text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def check(doc_path: Path, max_age: int, today: date) -> dict:
    if not doc_path.is_file():
        return {"ok": False, "error": f"file not found: {doc_path}"}
    text = doc_path.read_text(encoding="utf-8")
    verified = find_verified_date(text)
    if verified is None:
        return {"ok": False, "error": "no 'Verified ... YYYY-MM-DD' date found in header"}
    age = (today - verified).days
    ok = age <= max_age
    return {
        "check": "spec-currency",
        "ok": ok,
        "verified_date": verified.isoformat(),
        "age_days": age,
        "max_age_days": max_age,
        "file": str(doc_path),
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", type=Path, default=DOC, help="path to tool-compatibility.md")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE)
    ap.add_argument("--today", help="YYYY-MM-DD (testing)")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = check(args.doc, args.max_age_days, today)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
