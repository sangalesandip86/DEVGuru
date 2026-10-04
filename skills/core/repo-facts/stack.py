#!/usr/bin/env python3
"""Per-package stack fingerprint for monorepos (finding G1/G2).

Combines workspace detection with the existing stack_fingerprint.fingerprint() to produce
a stack.json with both root-level and per-package fingerprints.

Usage:
    python stack.py <repo_root> [--stdout] [--out DIR] [--max-files N]

Writes <repo_root>/.adlc/catalog/stack.json by default.
Exit codes: 0 = produced, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILLS_DIR / "testing" / "test-architecture" / "test-repo-discovery" / "scripts"))

from workspace import detect_workspace  # noqa: E402
from stack_fingerprint import fingerprint as root_fingerprint  # noqa: E402


def stack_with_packages(root: Path, max_files: int = 200_000) -> dict:
    ws = detect_workspace(root)
    root_fp = root_fingerprint(root, max_files)

    packages: list[dict] = []
    for pkg in ws.get("packages", []):
        pkg_path = root / pkg["path"]
        if pkg_path.is_dir():
            pkg_fp = root_fingerprint(pkg_path, max_files)
            packages.append({
                "name": pkg["name"],
                "path": pkg["path"],
                "stack": pkg_fp,
            })

    return {
        "classification": "FACT",
        "source": "stack.py",
        "root": root_fp,
        "packages": packages,
        "workspace_type": ws["workspace_type"],
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo_root")
    ap.add_argument("--max-files", type=int, default=200_000)
    ap.add_argument("--out", help="output directory (default: <repo_root>/.adlc/catalog)")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2
    result = stack_with_packages(root, args.max_files)
    if args.stdout:
        print(json.dumps(result, indent=2))
        return 0
    out = Path(args.out) if args.out else root / ".adlc" / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stack.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"stack": str(out / "stack.json"),
                      "workspace_type": result["workspace_type"],
                      "packages": len(result["packages"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
