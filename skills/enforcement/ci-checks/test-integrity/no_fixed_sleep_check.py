#!/usr/bin/env python3
"""No fixed sleeps in tests (plan §4.13 rule 6, REQ-QA-504).

Fixed sleeps make suites both slow and flaky. Waits must be tied to state instead: element
readiness, network idle, settled frames, or idling resources. This check greps test paths for
banned APIs in each language. It complements, and does not replace, linters such as
eslint-plugin-playwright `no-wait-for-timeout`.

Allowed exceptions are listed in a reviewed config file, never as inline comments:
    {"allow": [{"path_glob": "e2e/legacy/**", "rule": "js-settimeout", "reason": "..."}]}

Usage: no_fixed_sleep_check.py [PATH ...] [--config FILE]
Exit: 0 = clean, 1 = violations, 2 = bad input.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".dart_tool"}
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec|e2e|integration_test|androidTest|src/test|features|cypress|playwright|test_driver)/"
    r"|\.(spec|test|cy)\.[cm]?[jt]sx?$|_test\.(dart|py|go)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs|swift)$|_spec\.rb$|"
    r"(^|/)(steps?|step_definitions|stepdefinitions)/")

# (rule id, file-extension regex, banned pattern, suggestion)
RULES: list[tuple[str, re.Pattern, re.Pattern, str]] = [
    ("js-wait-for-timeout", re.compile(r"\.[cm]?[jt]sx?$"), re.compile(r"\.waitForTimeout\s*\("),
     "use web-first assertions (expect(locator).toBeVisible()) or waitForResponse/waitForURL"),
    ("js-cy-wait-number", re.compile(r"\.[cm]?[jt]sx?$"), re.compile(r"\bcy\.wait\(\s*\d"),
     "cy.wait('@alias') on an intercepted request, or an assertion that retries"),
    ("js-settimeout", re.compile(r"\.[cm]?[jt]sx?$"), re.compile(r"setTimeout\s*\([^)]*,\s*\d+\s*\)"),
     "await a condition (waitFor, expect.poll, detox waitFor().toBeVisible().withTimeout())"),
    ("js-pause", re.compile(r"\.[cm]?[jt]sx?$"), re.compile(r"\b(?:browser\.pause|driver\.sleep|\.pause)\s*\(\s*\d"),
     "use explicit waits (waitUntil / ExpectedConditions)"),
    ("py-time-sleep", re.compile(r"\.py$"), re.compile(r"\btime\.sleep\s*\(|(?<![\w.])sleep\s*\(\s*\d"),
     "poll a condition with a deadline, or use page.wait_for_* / expect(locator)"),
    ("py-asyncio-sleep", re.compile(r"\.py$"), re.compile(r"\basyncio\.sleep\s*\(\s*[1-9\.]"),
     "await the event/condition instead of sleeping"),
    ("py-wait-for-timeout", re.compile(r"\.py$"), re.compile(r"\.wait_for_timeout\s*\("),
     "use expect(locator).to_be_visible() or wait_for_response"),
    ("jvm-thread-sleep", re.compile(r"\.(java|kt)$"), re.compile(r"\b(?:Thread|SystemClock)\.sleep\s*\(|TimeUnit\.\w+\.sleep\s*\("),
     "Awaitility / WebDriverWait / Espresso IdlingResource / Compose waitUntil"),
    ("dart-future-delayed", re.compile(r"\.dart$"), re.compile(r"\bFuture\.delayed\s*\(|(?<![\w.])sleep\s*\(\s*(?:const\s+)?Duration"),
     "pumpAndSettle / pumpUntilFound helper / tester.pump(duration) under fake time"),
    ("go-time-sleep", re.compile(r"\.go$"), re.compile(r"\btime\.Sleep\s*\("),
     "use require.Eventually / channels / a fake clock"),
    ("cs-sleep", re.compile(r"\.cs$"), re.compile(r"\bThread\.Sleep\s*\(|\bTask\.Delay\s*\(\s*\d"),
     "use explicit waits or polling with a deadline"),
    ("swift-sleep", re.compile(r"\.swift$"), re.compile(r"(?<![\w.])(?:u?sleep|Thread\.sleep)\s*\("),
     "XCTWaiter / waitForExistence(timeout:) / expectation(for:)"),
    ("rb-sleep", re.compile(r"\.rb$"), re.compile(r"(?<![\w.])sleep[\s(]+\d"),
     "Capybara's waiting matchers (have_content, have_css)"),
]
COMMENT = re.compile(r"^\s*(//|#|\*|/\*)")


def load_allow(path: str | None) -> list[dict]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    allow = data.get("allow", [])
    for a in allow:
        if not a.get("path_glob") or not a.get("reason"):
            raise ValueError("each allow entry needs path_glob and reason")
    return allow


def allowed(rel: str, rule: str, allow: list[dict]) -> bool:
    return any(fnmatch.fnmatch(rel, a["path_glob"]) and a.get("rule", rule) == rule for a in allow)


def scan(paths: list[Path], allow: list[dict]) -> dict:
    violations, scanned = [], 0
    for base in paths:
        files = [base] if base.is_file() else sorted(base.rglob("*"))
        for p in files:
            if not p.is_file():
                continue
            rel = p.name if base.is_file() else p.relative_to(base).as_posix()
            if set(Path(rel).parts) & SKIP_DIRS or not TEST_PATH.search(rel if not base.is_file() else p.as_posix()):
                continue
            applicable = [r for r in RULES if r[1].search(p.name)]
            if not applicable:
                continue
            scanned += 1
            for lineno, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if COMMENT.match(line):
                    continue
                for rule, _, rx, hint in applicable:
                    if rx.search(line) and not allowed(rel, rule, allow):
                        violations.append({"rule": rule, "file": rel, "line": lineno,
                                           "code": line.strip()[:120], "use_instead": hint})
    return {"classification": "FACT", "source": "no_fixed_sleep_check.py", "files_scanned": scanned,
            "violations": violations, "verdict": "FAIL" if violations else "PASS"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--config")
    args = ap.parse_args(argv)
    try:
        allow = load_allow(args.config)
        paths = [Path(p) for p in args.paths]
        if any(not p.exists() for p in paths):
            raise ValueError("path not found")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    report = scan(paths, allow)
    print(json.dumps(report, indent=2))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
