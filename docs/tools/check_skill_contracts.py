#!/usr/bin/env python3
"""Check every skills/**/SKILL.md for the v3.1 skill entry contract (plan §4.14).

A valid SKILL.md has `stage`, `inputs`, `outputs` and `repo_roles` under frontmatter
`metadata`, with values from the vocabulary in docs/authoring-conventions.md, and a
`## Preflight` heading.

The vocabulary is read from docs/authoring-conventions.md, so the two can't drift.

Usage:  python docs/tools/check_skill_contracts.py [--root REPO] [--json]
Exit:   0 = all valid, 1 = offenders found, 2 = setup error
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

FIELDS = ("stage", "inputs", "outputs", "repo_roles")


def load_vocab(conventions: pathlib.Path) -> dict[str, set[str]]:
    text = conventions.read_text(encoding="utf-8")

    def first_backticked(prefix: str) -> set[str]:
        for line in text.splitlines():
            if line.startswith(prefix):
                groups = re.findall(r"`([^`]+)`", line)
                if groups:
                    # the vocabulary list is the longest backticked group on the line
                    return set(max(groups, key=len).split())
        raise ValueError(f"vocabulary line not found: {prefix!r}")

    stages = first_backticked("- Workflow stages") | {"CROSS_CUTTING"}
    return {
        "stage": stages,
        "repo_roles": first_backticked("- Repo roles"),
        "artifacts": first_backticked("- Artifact kinds"),
    }


def parse_metadata(text: str) -> dict[str, str] | None:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    meta: dict[str, str] = {}
    in_meta = False
    for line in m.group(1).splitlines():
        if line.startswith("metadata:"):
            in_meta = True
            continue
        if in_meta:
            if line.startswith("  ") and ":" in line:
                key, _, val = line.strip().partition(":")
                meta[key.strip()] = val.strip()
            elif line.strip() and not line.startswith(" "):
                in_meta = False
    return meta


def parse_list(raw: str) -> list[str] | None:
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return None
    inner = raw[1:-1].strip()
    return [x.strip().strip("'\"") for x in inner.split(",")] if inner else []


def check_file(path: pathlib.Path, vocab: dict[str, set[str]]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    meta = parse_metadata(text)
    if meta is None:
        return ["no frontmatter"]
    for field in FIELDS:
        if field not in meta:
            problems.append(f"missing metadata.{field}")
    if "stage" in meta and meta["stage"] not in vocab["stage"]:
        problems.append(f"invalid stage {meta['stage']!r}")
    for field, allowed in (("inputs", vocab["artifacts"]), ("outputs", vocab["artifacts"]),
                           ("repo_roles", vocab["repo_roles"])):
        if field not in meta:
            continue
        items = parse_list(meta[field])
        if items is None:
            problems.append(f"metadata.{field} is not a [list]")
            continue
        bad = [x for x in items if x not in allowed]
        if bad:
            problems.append(f"metadata.{field} has unknown values {bad}")
    if not re.search(r"^## Preflight\b", text, re.M):
        problems.append("missing '## Preflight' section")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=pathlib.Path(__file__).resolve().parents[2], type=pathlib.Path)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    conventions = args.root / "docs" / "authoring-conventions.md"
    try:
        vocab = load_vocab(conventions)
    except (OSError, ValueError) as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return 2

    files = sorted((args.root / "skills").rglob("SKILL.md"))
    offenders = {}
    for f in files:
        probs = check_file(f, vocab)
        if probs:
            offenders[f.relative_to(args.root).as_posix()] = probs

    if args.json:
        print(json.dumps({"checked": len(files), "valid": len(files) - len(offenders),
                          "offenders": offenders}, indent=2))
    else:
        for rel, probs in offenders.items():
            print(f"{rel}: {'; '.join(probs)}")
        print(f"checked {len(files)}, valid {len(files) - len(offenders)}, offenders {len(offenders)}")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
