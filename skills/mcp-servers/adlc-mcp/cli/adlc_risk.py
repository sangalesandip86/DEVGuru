#!/usr/bin/env python3
"""Risk scoring CLI. Wraps the quantitative risk scorer.

Usage:
    python adlc_risk.py --lines 200 --files 8
    python adlc_risk.py --lines 50 --files 3 --paths src/auth/login.py --churn 0.4 --coverage 0.6
    echo '{"lines_changed":50,"files_changed":3}' | python adlc_risk.py --stdin
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "skills" / "change-management" / "risk-tiering" / "scripts"))


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC risk scoring")
    parser.add_argument("--lines", type=int, default=0, help="Lines changed")
    parser.add_argument("--files", type=int, default=0, help="Files changed")
    parser.add_argument("--paths", nargs="*", default=[], help="Changed file paths")
    parser.add_argument("--churn", type=float, default=0.0, help="Churn ratio (0-1)")
    parser.add_argument("--coverage", type=float, default=1.0, help="Test coverage (0-1)")
    parser.add_argument("--stdin", action="store_true", help="Read JSON input from stdin")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    import risk_scorer

    if args.stdin:
        fixture = json.load(sys.stdin)
    else:
        fixture = {
            "lines_changed": args.lines,
            "files_changed": args.files,
            "file_paths": args.paths,
            "churn_ratio": args.churn,
            "coverage_gap": max(0.0, 1.0 - args.coverage),
        }

    result = risk_scorer.compute_risk_score(fixture)

    if args.pretty:
        print(f"Tier:     {result['tier']}")
        print(f"Score:    {result['score']:.4f}")
        print(f"Version:  {result.get('model_version', 'unknown')}")
        print("Features:")
        for k, v in result.get("features", {}).items():
            print(f"  {k:20s} {v:.4f}")
    else:
        json.dump(result, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
