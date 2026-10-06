#!/usr/bin/env python3
"""Deterministic regression replay runner.

Model-free: replays golden cases through real platform functions.
No LLM involved — pure function-level validation.

Usage:
    python replay_runner.py golden-cases/          # run all cases in directory
    python replay_runner.py golden-cases/risk.json  # run single case
    python replay_runner.py --check                 # built-in self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MAX_FIXTURE_SIZE = 256 * 1024  # 256 KB
MAX_STEPS = 80
MAX_CASES = 500

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "skills" / "change-management" / "risk-tiering" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "self-improvement" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "enforcement" / "lib"))


def _check_risk_routing(fixture: dict, expected: dict) -> tuple[bool, str]:
    import risk_scorer
    result = risk_scorer.compute_risk_score(fixture)
    if "tier" in expected and result["tier"] != expected["tier"]:
        return False, f"tier: expected {expected['tier']}, got {result['tier']} (score={result['score']})"
    if "score_min" in expected and result["score"] < expected["score_min"]:
        return False, f"score {result['score']} < min {expected['score_min']}"
    if "score_max" in expected and result["score"] > expected["score_max"]:
        return False, f"score {result['score']} > max {expected['score_max']}"
    return True, f"tier={result['tier']} score={result['score']:.4f}"


def _check_sensitive_path_detection(fixture: dict, expected: dict) -> tuple[bool, str]:
    import risk_scorer
    count = risk_scorer.count_sensitive_matches(fixture.get("file_paths", []))
    exp = expected.get("count", 0)
    if count != exp:
        return False, f"sensitive matches: expected {exp}, got {count}"
    return True, f"sensitive_matches={count}"


def _check_dangerous_path_blocking(fixture: dict, expected: dict) -> tuple[bool, str]:
    import adlc_enforcement as ae
    path = fixture.get("path", "")
    result = ae.match_dangerous_path(path)
    should_block = expected.get("blocked", True)
    if should_block and result is None:
        return False, f"expected '{path}' to be blocked, but it was allowed"
    if not should_block and result is not None:
        return False, f"expected '{path}' to be allowed, but it was blocked by {result}"
    return True, f"path={path} blocked={result is not None}"


def _check_bm25_ranking(fixture: dict, expected: dict) -> tuple[bool, str]:
    sys.path.insert(0, str(REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "src"))
    from adlc_mcp.modules.evidence_ledger.bm25 import bm25_search
    results = bm25_search(fixture.get("query", ""), fixture.get("corpus", []))
    if "top_id" in expected and results:
        if results[0].get("id") != expected["top_id"]:
            return False, f"top result id: expected {expected['top_id']}, got {results[0].get('id')}"
    if "min_results" in expected and len(results) < expected["min_results"]:
        return False, f"results: expected >= {expected['min_results']}, got {len(results)}"
    return True, f"results={len(results)}"


def _check_lesson_ranking(fixture: dict, expected: dict) -> tuple[bool, str]:
    import lesson_ranker
    results = lesson_ranker.rank_lessons(
        fixture.get("lessons", []),
        fixture.get("changed_files", []),
        fixture.get("task_description", ""),
    )
    if "top_title" in expected and results:
        if results[0].get("title") != expected["top_title"]:
            return False, f"top lesson: expected {expected['top_title']}, got {results[0].get('title')}"
    if "max_results" in expected and len(results) > expected["max_results"]:
        return False, f"too many results: {len(results)} > {expected['max_results']}"
    return True, f"results={len(results)}"


CHECKS = {
    "risk_routing": _check_risk_routing,
    "sensitive_path_detection": _check_sensitive_path_detection,
    "dangerous_path_blocking": _check_dangerous_path_blocking,
    "bm25_ranking": _check_bm25_ranking,
    "lesson_ranking": _check_lesson_ranking,
}


def load_case(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if len(text.encode()) > MAX_FIXTURE_SIZE:
        raise ValueError(f"fixture too large: {len(text.encode())} > {MAX_FIXTURE_SIZE}")
    case = json.loads(text)
    if len(case.get("steps", [])) > MAX_STEPS:
        raise ValueError(f"too many steps: {len(case['steps'])} > {MAX_STEPS}")
    return case


def run_case(case: dict) -> tuple[bool, list[dict]]:
    results = []
    all_pass = True
    for i, step in enumerate(case.get("steps", [])):
        action = step["action"]
        expected = step.get("expected", {})
        fixture = {**case.get("fixture", {}), **step.get("fixture_override", {})}
        check_fn = CHECKS.get(action)
        if check_fn is None:
            results.append({"step": i, "action": action, "ok": False, "detail": f"unknown check: {action}"})
            all_pass = False
            continue
        try:
            ok, detail = check_fn(fixture, expected)
        except Exception as exc:
            ok, detail = False, f"error: {exc}"
        results.append({"step": i, "action": action, "ok": ok, "detail": detail})
        if not ok:
            all_pass = False
    return all_pass, results


def run_suite(path: Path) -> tuple[int, int, list[dict]]:
    cases = []
    if path.is_file():
        cases = [path]
    elif path.is_dir():
        cases = sorted(path.glob("*.json"))
    if len(cases) > MAX_CASES:
        raise ValueError(f"too many cases: {len(cases)} > {MAX_CASES}")

    passed = 0
    failed = 0
    reports = []
    for case_path in cases:
        case = load_case(case_path)
        ok, results = run_case(case)
        reports.append({
            "case_id": case.get("case_id", case_path.stem),
            "ok": ok,
            "steps": results,
        })
        if ok:
            passed += 1
        else:
            failed += 1
    return passed, failed, reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic regression replay runner")
    parser.add_argument("path", nargs="?", help="Path to golden case file or directory")
    parser.add_argument("--check", action="store_true", help="Built-in self-test")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.check:
        case = {
            "case_id": "self-test",
            "fixture": {"lines_changed": 10, "files_changed": 2, "file_paths": ["src/main.py"]},
            "steps": [{"action": "risk_routing", "expected": {"tier": "LOW"}}],
        }
        ok, results = run_case(case)
        if ok:
            print(json.dumps({"status": "ok"}))
            return 0
        print(json.dumps({"status": "fail", "results": results}), file=sys.stderr)
        return 1

    if not args.path:
        parser.error("path is required (or use --check)")

    target = Path(args.path)
    passed, failed, reports = run_suite(target)

    if args.json:
        print(json.dumps({"passed": passed, "failed": failed, "reports": reports}, indent=2))
    else:
        for r in reports:
            status = "PASS" if r["ok"] else "FAIL"
            print(f"  {status}: {r['case_id']}")
            for s in r["steps"]:
                mark = "+" if s["ok"] else "-"
                print(f"    [{mark}] {s['action']}: {s['detail']}")
        print(f"\n{passed} passed, {failed} failed, {passed + failed} total")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
