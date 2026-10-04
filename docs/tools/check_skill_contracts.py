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
DESC_LIMIT = 160
BODY_HARD_LIMIT = 500
BODY_SOFT_LIMIT = 120


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


def parse_frontmatter(text: str) -> tuple[str | None, dict[str, str] | None]:
    """Return (description, metadata dict) from SKILL.md frontmatter."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None, None
    desc = None
    for line in m.group(1).splitlines():
        if line.startswith("description:"):
            desc = line.partition(":")[2].strip().strip("'\"")
            break
    return desc, _parse_meta_block(m.group(1))


def _parse_meta_block(block: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    in_meta = False
    for line in block.splitlines():
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


def check_file(path: pathlib.Path, vocab: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors fail the check; warnings are advisory."""
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    warnings: list[str] = []
    desc, meta = parse_frontmatter(text)
    if meta is None:
        return ["no frontmatter"], []
    if desc is not None and len(desc) > DESC_LIMIT:
        problems.append(f"description is {len(desc)} chars (limit {DESC_LIMIT})")
    elif desc is None:
        problems.append("missing description")
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
    body_start = re.search(r"^---\r?\n", text[3:], re.M)
    if body_start:
        body = text[3 + body_start.end():]
        body_lines = len(body.rstrip().splitlines())
        if body_lines > BODY_HARD_LIMIT:
            problems.append(f"body is {body_lines} lines (hard limit {BODY_HARD_LIMIT})")
        elif body_lines > BODY_SOFT_LIMIT:
            warnings.append(f"body is {body_lines} lines (soft target {BODY_SOFT_LIMIT})")
    enf_match = re.search(r"^## Enforcement\b", text, re.M)
    if not enf_match:
        problems.append("missing '## Enforcement' section")
    else:
        enf_text = text[enf_match.end():]
        next_h2 = re.search(r"^## ", enf_text, re.M)
        enf_body = enf_text[:next_h2.start()] if next_h2 else enf_text
        if not re.search(r"\b(Enforced|Detects|Guideline)\b", enf_body):
            warnings.append("## Enforcement has no label (expected Enforced, Detects, or Guideline)")
    return problems, warnings


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
    offenders: dict[str, list[str]] = {}
    warned: dict[str, list[str]] = {}
    for f in files:
        probs, warns = check_file(f, vocab)
        rel = f.relative_to(args.root).as_posix()
        if probs:
            offenders[rel] = probs
        if warns:
            warned[rel] = warns

    if args.json:
        print(json.dumps({"checked": len(files), "valid": len(files) - len(offenders),
                          "offenders": offenders, "warnings": warned}, indent=2))
    else:
        for rel, probs in offenders.items():
            print(f"{rel}: {'; '.join(probs)}")
        for rel, warns in warned.items():
            print(f"{rel}: [warning] {'; '.join(warns)}")
        print(f"checked {len(files)}, valid {len(files) - len(offenders)}, "
              f"offenders {len(offenders)}, warnings {len(warned)}")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
