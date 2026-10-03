#!/usr/bin/env python3
"""ac-coverage — maps passing tests to acceptance-criterion IDs (plan v3.1 §4.12).

This is what "acceptance criteria actually exercised" means for the self-improvement
positive-signal gate (plan §4.2) and for the DoD `ac_covered` item.

Tagging convention (any one is enough):
  * the AC id in the test name/title:      it("shows VaR [ST-101/AC-2]", ...)
  * an `@ac` comment/docstring on or just above/below the test definition:
        # @ac ST-101/AC-2 ST-101/AC-3
        def test_var_is_shown(): ...
  * the AC id in the JUnit testcase name (parametrised ids, BDD scenario names)

Test definitions recognised in source: Python `def test_*`, JS/TS `it(`/`test(`, Go
`func TestX(`, Java/Kotlin `@Test` + method. Results come from JUnit XML (any runner).

    python ac_coverage.py --tests tests/ --junit results.xml [--plans plans/] [--story ST-101]

Output JSON: {"acceptance_criteria": {AC: {tests, covered, passing, results}},
              "uncovered_automated": [...], "untagged_tests": n}
A test tagged in source but absent from every JUnit file counts as "not_run" — covered but
not passing. An AC is `passing` when at least one tagged test passed and none failed.

Exit codes: 0 always when inputs parse (the completion gate decides), 2 usage/input error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

AC_RE = re.compile(r"\bST-\d+/AC-\d+\b")
SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".cs", ".rb"}
DEF_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\("),                      # python
    re.compile(r"""\b(?:it|test)(?:\.\w+)?\s*\(\s*(['"`])(?P<title>.+?)\1"""),  # js/ts
    re.compile(r"^\s*func\s+(Test\w+)\s*\("),                                   # go
    re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+)?(?:suspend\s+)?(?:void|fun)\s+(\w+)\s*\("),  # java/kotlin
]
COMMENTISH = re.compile(r"^\s*(#|//|\*|/\*|\"\"\"|'''|@)")


def _test_name(line: str, prev_lines: list[str]) -> str | None:
    for i, pat in enumerate(DEF_PATTERNS):
        m = pat.search(line)
        if not m:
            continue
        if i == 1:
            return m.group("title")
        if i == 3 and not any("@Test" in p for p in prev_lines[-3:]):
            continue
        return m.group(1)
    return None


# Characterization tests pin current behaviour, not specified behaviour (ADR 0004 §3);
# they never count as AC verification even if they carry AC tags.
CHARACTERIZATION_RE = re.compile(r"characteri[sz]ation", re.IGNORECASE)


def scan_sources(roots: list[Path], excluded: set[str] | None = None) -> tuple[dict[str, set[str]], int]:
    """Return ({test_name: {AC ids}}, untagged_count); characterization tests go to `excluded`."""
    tagged: dict[str, set[str]] = {}
    untagged = 0
    excluded = excluded if excluded is not None else set()
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.suffix in SOURCE_EXT]
        for f in files:
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            last_def = -1
            for idx, line in enumerate(lines):
                name = _test_name(line, lines[max(0, idx - 3):idx])
                if name is None:
                    continue
                window = lines[max(last_def + 1, idx - 5):idx + 1]
                below = []
                for nxt in lines[idx + 1:idx + 4]:
                    if COMMENTISH.match(nxt):
                        below.append(nxt)
                    else:
                        break
                context = " ".join(window + below)
                ids = set(AC_RE.findall(context))
                last_def = idx
                if CHARACTERIZATION_RE.search(context):
                    excluded.add(name)
                    continue
                if ids:
                    tagged.setdefault(name, set()).update(ids)
                else:
                    untagged += 1
    return tagged, untagged


def parse_junit(paths: list[Path]) -> dict[str, str]:
    """Return {testcase name: PASSED|FAILED|SKIPPED}; a failure anywhere wins over a pass."""
    out: dict[str, str] = {}
    rank = {"PASSED": 0, "SKIPPED": 1, "FAILED": 2}
    for p in paths:
        root = ET.parse(p).getroot()
        for tc in root.iter("testcase"):
            name = tc.get("name", "")
            if tc.find("failure") is not None or tc.find("error") is not None:
                res = "FAILED"
            elif tc.find("skipped") is not None:
                res = "SKIPPED"
            else:
                res = "PASSED"
            if name not in out or rank[res] > rank[out[name]]:
                out[name] = res
    return out


def _results_for(test: str, junit: dict[str, str]) -> list[str]:
    hits = [r for n, r in junit.items()
            if n == test or n.startswith(test + "[") or n.startswith(test + " ") or n.endswith(" " + test)]
    return hits


def coverage(test_roots: list[Path], junit_paths: list[Path], plan_dir: Path | None = None,
             story: str | None = None) -> dict:
    excluded: set[str] = set()
    tagged, untagged = scan_sources(test_roots, excluded)
    junit = parse_junit(junit_paths)
    # JUnit names may carry AC ids directly (parametrised / BDD names)
    for name in junit:
        if CHARACTERIZATION_RE.search(name):
            excluded.add(name)
            continue
        ids = set(AC_RE.findall(name))
        if ids:
            tagged.setdefault(name, set()).update(ids)

    acs: dict[str, dict] = {}
    automated: list[str] = []
    if plan_dir is not None:
        import planning_lib as pl
        plans, _ = pl.load_plans(plan_dir)
        for sid, s in plans["story"].items():
            if story and sid != story:
                continue
            for a in s.get("acceptance_criteria") or []:
                acs[a["id"]] = {"tests": [], "results": {}, "verification": a.get("verification")}
                if a.get("verification") == "automated":
                    automated.append(a["id"])

    for test, ids in sorted(tagged.items()):
        for aid in ids:
            if story and not aid.startswith(story + "/"):
                continue
            entry = acs.setdefault(aid, {"tests": [], "results": {}})
            entry["tests"].append(test)
            res = _results_for(test, junit)
            entry["results"][test] = ("FAILED" if "FAILED" in res else
                                      "PASSED" if "PASSED" in res else
                                      "SKIPPED" if res else "NOT_RUN")
    for aid, e in acs.items():
        vals = list(e["results"].values())
        e["covered"] = bool(e["tests"])
        e["passing"] = "PASSED" in vals and "FAILED" not in vals
    return {
        "acceptance_criteria": dict(sorted(acs.items())),
        "uncovered_automated": sorted(a for a in automated if not acs[a]["passing"]),
        "untagged_tests": untagged,
        "excluded_characterization_tests": sorted(excluded),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Map tests to acceptance-criterion IDs.")
    ap.add_argument("--tests", action="append", default=[], help="test source dir/file (repeatable)")
    ap.add_argument("--junit", action="append", default=[], help="JUnit XML file (repeatable)")
    ap.add_argument("--plans", help="plans/ dir: report every AC, including uncovered ones")
    ap.add_argument("--story", help="limit to one story")
    args = ap.parse_args(argv)
    if not args.tests and not args.junit:
        ap.error("give at least one --tests or --junit")
    try:
        out = coverage([Path(t) for t in args.tests], [Path(j) for j in args.junit],
                       Path(args.plans) if args.plans else None, args.story)
    except (ET.ParseError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
