#!/usr/bin/env python3
"""Compute mandatory skill bindings from stack.json, story type and changed paths.

Reads the scope matrix rules deterministically and emits a binding set JSON.
LLM-selected skills are advisory; mandatory bindings must be computed.

Usage:
    python route.py --stack .adlc/catalog/stack.json --story-type UI_STORY
    python route.py --stack stack.json --paths src/auth/login.ts billing/api.py
    python route.py --stack stack.json --story-type API_CONTRACT --paths api/openapi.yaml --json
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

ALWAYS_MANDATORY = [
    "grounding/evidence-gate",
    "grounding/ambiguity-escalation",
    "grounding/trust-boundaries",
    "grounding/agent-failure-modes",
    "grounding/human-review-format",
    "core/evidence-ledger",
    "core/fact-classification",
    "governance/default-permissions",
    "self-improvement/failure-capture",
]

KEYWORD_TRIGGERS: list[tuple[list[str], list[str], list[str], str]] = [
    # (keywords, path_patterns, mandatory_skills, tier_floor)
    (
        ["payment", "billing", "invoice", "fee", "refund", "ledger"],
        ["payment/*", "billing/*"],
        ["testing/security-testing/sast-scanner", "testing/security-testing/secret-scanning"],
        "HIGH",
    ),
    (
        ["auth", "login", "token", "session", "permission", "rbac", "oauth", "password"],
        ["auth/*", "security/*"],
        ["testing/security-testing/sast-scanner", "testing/security-testing/secret-scanning"],
        "HIGH",
    ),
    (
        ["migration", "schema"],
        ["*/migrations/*", "*.sql"],
        ["change-management/risk-tiering", "change-management/snapshot"],
        "HIGH",
    ),
    (
        ["openapi", "proto", "graphql"],
        ["*.avsc", "**/openapi*", "**/*.proto"],
        ["contracts/compatibility-check", "testing/api-contract-testing/pact-consumer-driven"],
        "HIGH",
    ),
    (
        ["prompt", "llm", "agent"],
        [],
        ["testing/ai-agent-testing/ai-agent-test-design"],
        "HIGH",
    ),
]

STORY_TYPE_BINDINGS: dict[str, tuple[list[str], str]] = {
    "API_CONTRACT": (
        ["contracts/contract-registry", "contracts/compatibility-check",
         "testing/api-contract-testing/pact-consumer-driven"],
        "HIGH",
    ),
    "DATA_MIGRATION": (
        ["change-management/snapshot", "change-management/risk-tiering"],
        "HIGH",
    ),
    "SECURITY_STORY": (
        ["testing/security-testing/sast-scanner", "testing/security-testing/secret-scanning",
         "testing/security-testing/sca-dependency-audit"],
        "HIGH",
    ),
    "UI_STORY": (
        ["testing/web-ui-automation/playwright-expert", "testing/web-ui-automation/visual-regression"],
        "MEDIUM",
    ),
    "INFRASTRUCTURE": (
        ["change-management/snapshot", "testing/security-testing/deployment-verification"],
        "MEDIUM",
    ),
    "DOCUMENTATION": ([], "LOW"),
}

STACK_SKILL_MAP: dict[str, str] = {
    "playwright": "testing/web-ui-automation/playwright-expert",
    "selenium": "testing/web-ui-automation/selenium-expert",
    "webdriverio": "testing/web-ui-automation/selenium-expert",
    "flutter-integration_test": "testing/mobile-automation/flutter-testing",
    "flutter_test": "testing/mobile-automation/flutter-testing",
    "detox": "testing/mobile-automation/detox-react-native",
    "appium": "testing/mobile-automation/appium-expert",
    "xcuitest": "testing/mobile-automation/ios-xcuitest",
    "espresso": "testing/mobile-automation/android-espresso",
    "pact": "testing/api-contract-testing/pact-consumer-driven",
    "cucumber-js": "testing/test-design/bdd-feature-authoring",
    "cucumber-jvm": "testing/test-design/bdd-feature-authoring",
    "godog": "testing/test-design/bdd-feature-authoring",
    "behave": "testing/test-design/bdd-feature-authoring",
    "pytest-bdd": "testing/test-design/bdd-feature-authoring",
    "cucumber-rs": "testing/test-design/bdd-feature-authoring",
}


def _path_matches(path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path.split("/")[-1], pat):
            return True
    return False


def route(stack: dict, story_type: str | None = None,
          paths: list[str] | None = None) -> dict:
    bindings: list[str] = list(ALWAYS_MANDATORY)
    roles: set[str] = set()
    tier_floor = "LOW"
    triggers: list[str] = []

    tier_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def raise_tier(new: str) -> None:
        nonlocal tier_floor
        if tier_order.get(new, 0) > tier_order.get(tier_floor, 0):
            tier_floor = new

    def add(skills: list[str], trigger: str) -> None:
        for s in skills:
            if s not in bindings:
                bindings.append(s)
        if trigger not in triggers:
            triggers.append(trigger)

    if story_type and story_type in STORY_TYPE_BINDINGS:
        skills, floor = STORY_TYPE_BINDINGS[story_type]
        add(skills, f"story_type={story_type}")
        raise_tier(floor)

    path_text = " ".join(paths or []).lower()
    for keywords, path_patterns, skills, floor in KEYWORD_TRIGGERS:
        matched = any(kw in path_text for kw in keywords)
        if not matched and paths:
            matched = any(_path_matches(p, path_patterns) for p in paths)
        if matched:
            add(skills, f"keyword={keywords[0]}")
            raise_tier(floor)

    if paths and any(not p.endswith((".md", ".txt", ".rst")) for p in paths):
        roles.update(["code-reviewer", "qa-derive", "qa-diagnose"])
        add([], "code_change")

    for cat in ("e2e_driver", "unit_runner", "bdd", "contract_testing"):
        for tool in stack.get(cat, []):
            skill = STACK_SKILL_MAP.get(tool)
            if skill:
                add([skill], f"stack:{tool}")

    for pkg in stack.get("packages", []):
        pkg_stack = pkg.get("stack", {})
        for cat in ("e2e_driver", "unit_runner", "bdd", "contract_testing"):
            for tool in pkg_stack.get(cat, []):
                skill = STACK_SKILL_MAP.get(tool)
                if skill:
                    add([skill], f"stack:{pkg.get('name', '?')}:{tool}")

    return {
        "bindings": bindings,
        "roles": sorted(roles),
        "tier_floor": tier_floor,
        "triggers": triggers,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", required=True, help="path to stack.json")
    ap.add_argument("--story-type", help="story type (API_CONTRACT, UI_STORY, etc.)")
    ap.add_argument("--paths", nargs="*", help="changed file paths")
    ap.add_argument("--json", action="store_true", help="compact JSON output")
    args = ap.parse_args(argv)

    try:
        stack = json.loads(Path(args.stack).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    result = route(stack, args.story_type, args.paths)
    indent = None if args.json else 2
    print(json.dumps(result, indent=indent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
