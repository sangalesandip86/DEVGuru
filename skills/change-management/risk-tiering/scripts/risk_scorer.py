#!/usr/bin/env python3
"""Quantitative risk scoring for Change Sets.

Logistic regression: score = sigmoid(bias + sum(weight * feature))
Maps to DEVGuru's 4-tier model (LOW/MEDIUM/HIGH/CRITICAL).

Usage:
    echo '{"lines_changed":50,"files_changed":3,"file_paths":["src/main.py"]}' | python risk_scorer.py
    python risk_scorer.py --check   # built-in self-tests
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from fnmatch import fnmatch

MODEL_VERSION = "1.0.0"

BIAS = -3.2
WEIGHTS = {
    "lines_changed": 1.8,
    "files_changed": 1.2,
    "churn_ratio": 1.5,
    "coverage_gap": 2.0,
    "sensitive_paths": 2.5,
}

SENSITIVE_PATTERNS = [
    "**/auth/**", "**/security/**", "**/*secret*", "**/migrations/**",
    "**/.github/workflows/**", "**/Dockerfile", "**/pom.xml",
    "**/package.json", "**/payment/**", "**/billing/**",
    "**/iac/**", "**/terraform/**",
]

TIER_BOUNDARIES = [
    (0.75, "CRITICAL"),
    (0.50, "HIGH"),
    (0.25, "MEDIUM"),
    (0.00, "LOW"),
]


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def log_scale(value: float, reference: float = 10.0) -> float:
    """Scale a non-negative value to [0, 1] using log. log_scale(0)=0, log_scale(reference)=1."""
    if value <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(reference), 1.0)


def count_sensitive_matches(file_paths: list[str]) -> int:
    count = 0
    for fp in file_paths:
        normalized = fp.replace("\\", "/")
        for pattern in SENSITIVE_PATTERNS:
            if fnmatch(normalized, pattern):
                count += 1
                break
    return count


def compute_risk_score(data: dict) -> dict:
    lines = max(int(data.get("lines_changed", 0)), 0)
    files = max(int(data.get("files_changed", 0)), 0)
    churn = max(float(data.get("churn_ratio", 0.0)), 0.0)
    coverage_gap = max(float(data.get("coverage_gap", 0.0)), 0.0)
    file_paths = data.get("file_paths", [])

    sensitive_count = count_sensitive_matches(file_paths)

    features = {
        "lines_changed": log_scale(lines, 1000),
        "files_changed": log_scale(files, 50),
        "churn_ratio": min(churn, 1.0),
        "coverage_gap": min(coverage_gap, 1.0),
        "sensitive_paths": log_scale(sensitive_count, 5),
    }

    z = BIAS + sum(WEIGHTS[k] * features[k] for k in WEIGHTS)
    score = sigmoid(z)

    tier = "HIGH"  # fail-safe default
    for threshold, name in TIER_BOUNDARIES:
        if score >= threshold:
            tier = name
            break

    return {
        "score": round(score, 4),
        "tier": tier,
        "features": {k: round(v, 4) for k, v in features.items()},
        "sensitive_matches": sensitive_count,
        "model_version": MODEL_VERSION,
    }


def _check() -> bool:
    cases = [
        ({"lines_changed": 10, "files_changed": 2, "file_paths": ["src/main.py"]},
         "LOW", 0.0, 0.25),
        ({"lines_changed": 200, "files_changed": 8, "churn_ratio": 0.3, "file_paths": ["src/app.py"]},
         "MEDIUM", 0.25, 0.50),
        ({"lines_changed": 500, "files_changed": 15, "file_paths": ["src/payment/charge.py"]},
         "HIGH", 0.50, 0.75),
        ({"lines_changed": 2000, "files_changed": 50,
          "file_paths": ["src/auth/login.py", "db/migrations/001.sql", "src/billing/invoice.py"]},
         "CRITICAL", 0.75, 1.0),
    ]
    ok = True
    for data, expected_tier, low, high in cases:
        result = compute_risk_score(data)
        if result["tier"] != expected_tier:
            print(f"FAIL: expected tier {expected_tier}, got {result['tier']} (score={result['score']})", file=sys.stderr)
            ok = False
        if not (low <= result["score"] < high + 0.001):
            print(f"FAIL: score {result['score']} not in [{low}, {high}] for tier {expected_tier}", file=sys.stderr)
            ok = False

    assert sigmoid(0) == 0.5
    assert sigmoid(10) > sigmoid(5)
    assert log_scale(0) == 0.0
    assert log_scale(10) == 1.0
    assert compute_risk_score({})["model_version"] == MODEL_VERSION

    if ok:
        print(json.dumps({"status": "ok", "cases": len(cases)}))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantitative risk scoring for Change Sets")
    parser.add_argument("--check", action="store_true", help="Run built-in self-tests")
    args = parser.parse_args()

    if args.check:
        return 0 if _check() else 1

    data = json.load(sys.stdin)
    result = compute_risk_score(data)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
