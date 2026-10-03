#!/usr/bin/env python3
"""Catalogue shared test assets and rank golden samples (plan §4.13 step 1).

Produces:
  * fixtures / builders / factories
  * page objects / screen robots
  * step-definition PATTERNS (phrases only, never bodies — safe for code-blind qa-derive)
  * duplicate step patterns (a DuplicateStepDefinition risk)
  * ranked golden samples: passing in CI, not skipped, not flaky, recent, using shared helpers

Optional evidence inputs:
  --junit FILE...     JUnit XML of the last CI run (a file with any failing case is excluded)
  --flaky FILE        flaky-detector.py JSON (files with flaky tests are excluded)
  --git               use `git log` (local only) for recency

Outputs (default directory <repo_root>/.adlc/catalog, override with --out):
  test-assets.json    full catalogue — test-engineer / qa-diagnose
  step-patterns.json  phrases only (keyword + pattern, no paths/bodies) — the ONLY file qa-derive may read

Usage:
    test_asset_catalog.py <repo_root> [--junit a.xml ...] [--flaky flaky.json] [--git]
        [--top N] [--out DIR] [--stdout]

Exit codes: 0 = catalogue produced, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "out",
    ".dart_tool", "Pods", "vendor", ".gradle", ".next", "coverage", "bin", "obj",
}
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".dart", ".py", ".java", ".kt", ".cs",
            ".go", ".rb", ".swift"}

FIXTURE_DIRS = {"fixtures", "__fixtures__", "factories", "builders", "testdata", "test-data",
                "test_data", "mocks", "__mocks__", "seeds", "seed"}
FIXTURE_FILE = re.compile(
    r"(Builder|Factory|Fixtures?|Mother)\.[A-Za-z]+$|\.fixtures?\.[A-Za-z]+$|_test_data\.[A-Za-z]+$"
    r"|(^|/)(factories|fixtures|conftest)\.py$|_builder\.(dart|py)$|_factory\.(dart|py)$")
PAGE_DIRS = {"pages", "page-objects", "pageobjects", "page_objects", "robots", "screens", "screen-objects"}
PAGE_FILE = re.compile(r"(Page|Screen|Robot|PO)\.[A-Za-z]+$|_(page|screen|robot)\.[A-Za-z]+$|\.page\.[jt]s$")

TEST_FILE = re.compile(
    r"\.(spec|test|cy)\.[cm]?[jt]sx?$|_test\.(dart|py|go)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs|swift)$|_spec\.rb$")
SKIP_MARKERS = re.compile(
    r"\b(describe|it|test|context)\.(skip|todo|fixme)\b|\bx(it|describe|test)\s*\(|@Disabled\b|@Ignore\b"
    r"|pytest\.mark\.skip|@unittest\.skip|\bskip\s*:\s*true\b|t\.Skip\(|\[Ignore\]|\[Fact\(Skip\s*=|@pytest\.mark\.xfail")

# Step-definition extractors: (framework, regex). Group "kw" = keyword, "pat" = pattern.
STEP_EXTRACTORS: list[tuple[str, re.Pattern]] = [
    ("cucumber-js", re.compile(
        r"\b(?P<kw>Given|When|Then|And|But|defineStep|Step)\s*\(\s*"
        r"(?:(?P<q>['\"`])(?P<pat>(?:\\.|(?!(?P=q)).)*)(?P=q)|/(?P<rx>(?:\\/|[^/\n])+)/[gimsuy]*)")),
    ("cucumber-jvm", re.compile(
        r"@(?P<kw>Given|When|Then|And|But|Step)\s*\(\s*\"(?P<pat>(?:\\.|[^\"\\])*)\"")),
    ("behave/pytest-bdd", re.compile(
        r"@(?P<kw>given|when|then|step)\s*\(\s*(?:parsers\.\w+\(\s*)?[rbu]*(?P<q>['\"])(?P<pat>(?:\\.|(?!(?P=q)).)*)(?P=q)")),
    ("specflow/reqnroll", re.compile(
        r"\[\s*(?P<kw>Given|When|Then|StepDefinition)\s*\(\s*@?\"(?P<pat>(?:\"\"|[^\"])*)\"")),
    ("dart-gherkin", re.compile(
        r"\b(?P<kw>given|when|then|and|but)\d?\s*(?:<[^>()]*>)?\s*\(\s*r?(?P<q>['\"])(?P<pat>(?:\\.|(?!(?P=q)).)*)(?P=q)")),
    ("godog", re.compile(
        r"\.Step\(\s*`(?P<pat>[^`]*)`")),
]
STEP_FILE_HINT = re.compile(r"steps?|step_?def|stepdefinitions|features|glue", re.I)


def iter_files(root: Path):
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS:
                    stack.append(p)
            elif p.is_file():
                yield p


def read(p: Path) -> str:
    try:
        return p.read_bytes()[:1_000_000].decode("utf-8", errors="replace")
    except OSError:
        return ""


def normalize_step(pattern: str) -> str:
    """Normalize a step pattern so equivalent definitions compare equal."""
    s = pattern.strip().strip("^$")
    s = re.sub(r"\{[a-zA-Z_]*\}", "{}", s)                  # cucumber expressions
    s = re.sub(r"\([^)]*\)", "{}", s)                        # regex capture groups
    s = re.sub(r"<[^>]+>", "{}", s)                           # SpecFlow / outline params
    s = re.sub(r"\s+", " ", s).lower()
    return s


def extract_steps(rel: str, text: str) -> list[dict]:
    steps = []
    if not STEP_FILE_HINT.search(rel) and not re.search(r"@(Given|When|Then)|\b(Given|When|Then)\s*\(|\[Given", text):
        return steps
    for framework, rx in STEP_EXTRACTORS:
        if framework == "dart-gherkin" and not rel.endswith(".dart"):
            continue
        if framework == "behave/pytest-bdd" and not rel.endswith(".py"):
            continue
        if framework == "cucumber-jvm" and not rel.endswith((".java", ".kt")):
            continue
        if framework == "specflow/reqnroll" and not rel.endswith(".cs"):
            continue
        if framework == "cucumber-js" and not re.search(r"\.[cm]?[jt]sx?$", rel):
            continue
        if framework == "godog" and not rel.endswith(".go"):
            continue
        for m in rx.finditer(text):
            pat = m.groupdict().get("pat")
            if pat is None:
                pat = m.groupdict().get("rx") or ""
            line = text.count("\n", 0, m.start()) + 1
            steps.append({
                "framework": framework,
                "keyword": m.group("kw").capitalize() if "kw" in m.groupdict() and m.group("kw") else "Step",
                "pattern": pat,
                "normalized": normalize_step(pat),
                "file": rel,
                "line": line,
            })
    return steps


def load_junit(paths: list[str]) -> tuple[set[str], set[str]]:
    """Return (failing identifiers, passing identifiers) — classnames/files, lower-cased."""
    failing, passing = set(), set()
    for path in paths:
        root = ET.parse(path).getroot()
        for case in root.iter("testcase"):
            ident = (case.get("file") or case.get("classname") or "").lower()
            if not ident:
                continue
            if case.find("failure") is not None or case.find("error") is not None:
                failing.add(ident)
            elif case.find("skipped") is None:
                passing.add(ident)
    return failing, passing


def load_flaky(path: str | None) -> set[str]:
    if not path:
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = set()
    for t in data.get("flaky", []):
        cls = t["test"].split("::")[0].lower()
        if cls:
            out.add(cls)
    return out


def ident_matches(rel: str, idents: set[str]) -> bool:
    """Does a JUnit classname/file identifier refer to this test file?"""
    rel_l = rel.lower()
    stem = Path(rel).stem.lower().split(".")[0]
    dotted = re.sub(r"\.[^.]+$", "", rel_l).replace("/", ".")
    for i in idents:
        if i == rel_l or rel_l.endswith(i) or i.endswith(dotted) or i.split(".")[-1] == stem or i.endswith("/" + Path(rel_l).name):
            return True
    return False


def git_recency(root: Path, rel: str) -> int:
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct", "--", rel],
                             capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def catalog(root: Path, junit: list[str] | None = None, flaky: str | None = None,
            use_git: bool = False, top: int = 3) -> dict:
    fixtures, pages, steps, tests = [], [], [], []
    for p in iter_files(root):
        rel = p.relative_to(root).as_posix()
        if p.suffix not in CODE_EXT and p.suffix not in {".json", ".yaml", ".yml", ".csv"}:
            continue
        comps = {c.lower() for c in rel.split("/")[:-1]}
        if comps & FIXTURE_DIRS or FIXTURE_FILE.search(rel):
            fixtures.append(rel)
        if p.suffix in CODE_EXT and (comps & PAGE_DIRS or PAGE_FILE.search(p.name)) and not TEST_FILE.search(rel):
            pages.append(rel)
        if p.suffix in CODE_EXT:
            text = read(p)
            steps.extend(extract_steps(rel, text))
            if TEST_FILE.search(rel):
                tests.append((rel, text))

    # duplicates
    by_norm = defaultdict(list)
    for s in steps:
        by_norm[s["normalized"]].append(f'{s["file"]}:{s["line"]}')
    duplicates = [{"normalized": k, "locations": v} for k, v in sorted(by_norm.items()) if len(v) > 1]

    # golden-sample ranking
    failing, passing = load_junit(junit or [])
    flaky_ids = load_flaky(flaky)
    helper_names = {Path(a).stem.split(".")[0].lower() for a in fixtures + pages}
    candidates, excluded = [], []
    for rel, text in tests:
        reason = None
        if SKIP_MARKERS.search(text):
            reason = "contains skip/xfail markers"
        elif failing and ident_matches(rel, failing):
            reason = "failing in supplied CI results"
        elif flaky_ids and ident_matches(rel, flaky_ids):
            reason = "flaky per flaky-detector"
        if reason:
            excluded.append({"file": rel, "reason": reason})
            continue
        words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower()))
        helper_use = len(helper_names & words)
        assertions = len(re.findall(r"\b(expect|assert\w*|should|verify|XCTAssert\w*)\b", text))
        score = 0.0
        score += 3.0 if (passing and ident_matches(rel, passing)) else 0.0
        score += min(helper_use, 5) * 1.0
        score += 1.0 if assertions > 0 else -5.0
        recency = git_recency(root, rel) if use_git else 0
        candidates.append({"file": rel, "score": score, "helper_refs": helper_use,
                           "assertion_count": assertions, "last_commit_ts": recency,
                           "suffix": _suffix_label(rel)})
    groups = defaultdict(list)
    for c in candidates:
        groups[c["suffix"]].append(c)
    golden = {}
    for suffix, items in sorted(groups.items()):
        items.sort(key=lambda c: (-c["score"], -c["last_commit_ts"], c["file"]))
        golden[suffix] = items[:top]

    return {
        "classification": "FACT",
        "source": "test_asset_catalog.py",
        "fixtures": sorted(fixtures),
        "page_objects": sorted(pages),
        "step_patterns": [{k: s[k] for k in ("framework", "keyword", "pattern", "file", "line")} for s in steps],
        "duplicate_steps": duplicates,
        "golden_samples": golden,
        "excluded_samples": excluded,
        "evidence_used": {"junit": bool(junit), "flaky": bool(flaky), "git": use_git},
    }


def _suffix_label(rel: str) -> str:
    m = re.search(r"(\.(?:spec|test|cy)\.[cm]?[jt]sx?|_test\.(?:dart|py|go)|Tests?\.(?:java|kt|cs|swift)|_spec\.rb)$", rel)
    if m:
        return "*" + m.group(1)
    if re.search(r"(^|/)test_[^/]*\.py$", rel):
        return "test_*.py"
    return "other"


def step_pattern_view(result: dict) -> dict:
    """The phrases-only view qa-derive may read: no file paths, lines or bodies."""
    seen, patterns = set(), []
    for s in result["step_patterns"]:
        key = (s["keyword"], s["pattern"])
        if key not in seen:
            seen.add(key)
            patterns.append({"keyword": s["keyword"], "pattern": s["pattern"]})
    return {
        "classification": "FACT",
        "source": "test_asset_catalog.py (step-pattern view)",
        "step_patterns": patterns,
        "duplicate_steps": [{"normalized": d["normalized"], "count": len(d["locations"])}
                            for d in result["duplicate_steps"]],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo_root")
    ap.add_argument("--junit", nargs="*", default=[])
    ap.add_argument("--flaky")
    ap.add_argument("--git", action="store_true")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--out", help="output directory (default: <repo_root>/.adlc/catalog). Writes "
                    "test-assets.json (full catalogue) and step-patterns.json (phrases only).")
    ap.add_argument("--stdout", action="store_true", help="print the full catalogue instead of writing files")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2
    try:
        result = catalog(root, args.junit, args.flaky, args.git, args.top)
    except (ET.ParseError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": f"bad evidence input: {exc}"}), file=sys.stderr)
        return 2
    if args.stdout:
        print(json.dumps(result, indent=2))
        return 0
    out = Path(args.out) if args.out else root / ".adlc" / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    assets_path, steps_path = out / "test-assets.json", out / "step-patterns.json"
    assets_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    steps_path.write_text(json.dumps(step_pattern_view(result), indent=2), encoding="utf-8")
    print(json.dumps({"test_assets": str(assets_path), "step_patterns": str(steps_path),
                      "counts": {"fixtures": len(result["fixtures"]), "page_objects": len(result["page_objects"]),
                                 "step_patterns": len(result["step_patterns"]),
                                 "duplicate_steps": len(result["duplicate_steps"])}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
