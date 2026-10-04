#!/usr/bin/env python3
"""Compute verification strength from flake rate, mutation score, and coverage.

Verification strength is used by autonomy gating to decide how much latitude an
agent gets. Higher verification strength = more autonomy is safe.

Score = weighted harmonic mean of three signals:
  - coverage  (0-100, weight 1)
  - mutation  (0-100, weight 2)  — mutation is the strongest signal
  - stability (0-100, weight 1)  — 100 - flake_rate

Usage:
    python verification_strength.py --coverage 85 --mutation 60 --flake-rate 2.5
    python verification_strength.py --json '{"coverage":85,"mutation":60,"flake_rate":2.5}'
"""
from __future__ import annotations

import argparse
import json
import sys

THRESHOLDS = {
    "HIGH":   70,
    "MEDIUM": 40,
    "LOW":    0,
}


def verification_strength(coverage: float, mutation: float, flake_rate: float) -> dict:
    stability = max(0.0, 100.0 - flake_rate)
    weights = {"coverage": 1, "mutation": 2, "stability": 1}
    signals = {"coverage": coverage, "mutation": mutation, "stability": stability}

    total_weight = sum(weights.values())
    weighted_sum = sum(weights[k] * signals[k] for k in weights)

    numerator = total_weight
    denominator = sum(weights[k] / max(signals[k], 0.01) for k in weights)
    harmonic = numerator / denominator if denominator > 0 else 0

    arithmetic = weighted_sum / total_weight if total_weight else 0
    score = round((harmonic + arithmetic) / 2, 1)

    tier = "LOW"
    for t, threshold in sorted(THRESHOLDS.items(), key=lambda x: -x[1]):
        if score >= threshold:
            tier = t
            break

    return {
        "score": score,
        "tier": tier,
        "signals": signals,
        "weights": weights,
        "thresholds": THRESHOLDS,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coverage", type=float, default=0)
    ap.add_argument("--mutation", type=float, default=0)
    ap.add_argument("--flake-rate", type=float, default=0)
    ap.add_argument("--json", dest="json_input", help="JSON object with coverage, mutation, flake_rate")
    args = ap.parse_args(argv)

    if args.json_input:
        data = json.loads(args.json_input)
        coverage = data.get("coverage", 0)
        mutation = data.get("mutation", 0)
        flake_rate = data.get("flake_rate", 0)
    else:
        coverage = args.coverage
        mutation = args.mutation
        flake_rate = args.flake_rate

    result = verification_strength(coverage, mutation, flake_rate)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
