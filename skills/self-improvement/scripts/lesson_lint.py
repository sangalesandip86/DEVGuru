#!/usr/bin/env python3
"""Lint a self-improvement lesson (ADR 0006 §2).

A lesson is rejected unless:
  * it validates against reference/lesson.schema.json;
  * `skill` exists in the catalog (skills/<skill>/SKILL.md) and `step` names a heading or a
    numbered step of that SKILL.md ("Procedure 4 — write acceptance criteria");
  * `failure_class` is in the taxonomy (failure-class-map.json `classes`);
  * `advice` is checkable: it states a condition and an observable/threshold, and contains no
    vague phrasing ("be careful", "make sure to consider", ...);
  * GATE/LINT remedies have a mechanical `check`.
Warnings: a mechanical `check` with a SKILL_TEXT/EXAMPLE remedy and no rationale (prefer
GATE/LINT); `last_fired` older than 6 months (prune candidate); repro file not found for a DRAFT.

Usage:  python lesson_lint.py LESSON.(json|yaml) [...] [--catalog skills/] [--today YYYY-MM-DD]
Output: JSON list of {file, lesson_id, result, errors, warnings}
Exit:   0 all PASS, 1 any FAIL, 2 usage/setup error
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _schema_lite import load_schema, validate  # noqa: E402

REPO = HERE.parents[2]
SCHEMA = HERE.parent / "improvement-review" / "reference" / "lesson.schema.json"
CLASS_MAP = HERE.parent / "failure-capture" / "reference" / "failure-class-map.json"
PRUNE_AFTER_DAYS = 182

BANNED = [
    "be careful", "make sure to consider", "make sure to think", "consider whether", "think about",
    "pay attention", "be mindful", "keep in mind", "try to", "where appropriate", "as appropriate",
    "as needed", "if necessary", "when necessary", "best practice", "properly", "appropriately",
    "be aware", "remember to", "don't forget", "do not forget", "ensure quality", "be thorough",
    "use common sense", "use judgment", "use judgement",
]
CONDITION = re.compile(r"\b(when|whenever|if|unless|for (each|every|any)|each|every|before|after|once)\b", re.I)
OBSERVABLE = re.compile(
    r"\d|[≥≤<>=]|\b(at least|at most|exactly|no more than|none|zero|all|must|require[sd]?|reject|block|fail|"
    r"record|cite|list|include|add|tag|mark|link|state|count|name)\b", re.I)
STOP = {"with", "from", "that", "this", "into", "when", "each", "every", "step", "the", "and", "for"}


def load_doc(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    sys.path.insert(0, str(REPO / "skills" / "enforcement" / "ci-checks" / "planning-gates"))
    try:
        import minyaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - repo layout
        raise ValueError("not JSON and no YAML loader available") from exc
    return minyaml.loads(text)


def norm(s: str) -> str:
    s = s.lower().replace("—", " ").replace("–", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_skill(md: str) -> tuple[list[str], dict[str, dict[int, str]]]:
    """Return (headings, {normalized_h2: {n: item_text}})."""
    headings: list[str] = []
    steps: dict[str, dict[int, str]] = {}
    section, current = "", None
    in_front = md.startswith("---")
    for i, line in enumerate(md.splitlines()):
        if in_front:
            if i > 0 and line.strip() == "---":
                in_front = False
            continue
        h = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if h:
            headings.append(h.group(1))
            if line.startswith("## "):
                section = norm(h.group(1))
                steps.setdefault(section, {})
            current = None
            continue
        item = re.match(r"^(\d+)\.\s+(.*)$", line)
        if item and section:
            current = int(item.group(1))
            steps[section][current] = item.group(2)
        elif current is not None and line.startswith("   ") and line.strip():
            steps[section][current] += " " + line.strip()
        elif not line.strip():
            current = None
    return headings, steps


def _stems(text: str) -> set[str]:
    return {w[:5] for w in norm(text).split() if len(w) >= 4 and w not in STOP}


def step_matches(step: str, md: str) -> str | None:
    """None if `step` names a heading or numbered step of the SKILL.md, else a reason."""
    headings, steps = parse_skill(md)
    nheads = {norm(h) for h in headings}
    if norm(step) in nheads:
        return None
    parts = re.split(r"\s+[—–-]\s+|:\s+", step, maxsplit=1)
    head, desc = parts[0], (parts[1] if len(parts) > 1 else "")
    m = re.match(r"^(.*?)\s*(?:step\s*)?#?(\d+)$", head.strip(), re.I)
    if m:
        sec = norm(m.group(1))
        n = int(m.group(2))
        candidates = [s for s in steps if s == sec or s.startswith(sec + " ")] if sec else list(steps)
        for s in candidates:
            if n in steps[s]:
                if not desc:
                    return None
                want, have = _stems(desc), _stems(steps[s][n])
                if not want or len(want & have) * 2 >= len(want):
                    return None
                return f"step text {desc!r} does not match {s!r} item {n}: {steps[s][n][:80]!r}"
        return f"no numbered step {n} under a heading matching {m.group(1)!r}"
    if norm(head) in nheads:
        return None
    return f"step {step!r} is not a heading or numbered step of the skill"


def lint(lesson: dict, catalog: Path, classes: list[str], schema: dict, today: dt.date) -> tuple[list[str], list[str]]:
    errors = validate(lesson, schema)
    warnings: list[str] = []
    if not isinstance(lesson, dict):
        return errors or ["lesson is not an object"], warnings

    skill = lesson.get("skill")
    if isinstance(skill, str):
        md_path = catalog / skill / "SKILL.md"
        if ".." in Path(skill).parts or not md_path.is_file():
            errors.append(f"skill {skill!r} not found in catalog ({md_path.as_posix()})")
        elif isinstance(lesson.get("step"), str):
            reason = step_matches(lesson["step"], md_path.read_text(encoding="utf-8"))
            if reason:
                errors.append(reason)

    if lesson.get("failure_class") not in classes:
        errors.append(f"failure_class {lesson.get('failure_class')!r} not in taxonomy")

    advice = lesson.get("advice")
    if isinstance(advice, str):
        low = advice.lower()
        for phrase in BANNED:
            if phrase in low:
                errors.append(f"advice uses vague phrase {phrase!r}")
        if not CONDITION.search(advice):
            errors.append("advice has no condition (when/if/for each/before/...)")
        if not OBSERVABLE.search(advice):
            errors.append("advice has no observable or threshold (number, comparison, require/reject/record/...)")

    kind, check = lesson.get("remedy_kind"), (lesson.get("check") or "").strip()
    target = lesson.get("remedy_target") or {}
    if kind in ("GATE", "LINT") and not check:
        errors.append(f"remedy_kind {kind} needs a mechanical `check`")
    if kind in ("SKILL_TEXT", "EXAMPLE") and check and not target.get("rationale"):
        warnings.append("lesson has a mechanical `check`; prefer GATE/LINT or give remedy_target.rationale")

    last = lesson.get("last_fired")
    if isinstance(last, str):
        try:
            age = (today - dt.date.fromisoformat(last[:10])).days
            if age > PRUNE_AFTER_DAYS:
                warnings.append(f"PRUNE_CANDIDATE: last fired {age} days ago")
        except ValueError:
            errors.append(f"last_fired {last!r} is not an ISO date")

    repro = lesson.get("repro") or {}
    evals_path = repro.get("evals_path")
    if isinstance(evals_path, str):
        p = (REPO / evals_path) if not Path(evals_path).is_absolute() else Path(evals_path)
        msg = None
        if not p.is_file():
            msg = f"repro evals file not found: {evals_path}"
        else:
            try:
                ids = [e.get("id") for e in json.loads(p.read_text(encoding="utf-8")).get("evals", [])]
                if repro.get("eval_id") not in ids:
                    msg = f"eval_id {repro.get('eval_id')!r} not in {evals_path}"
            except (json.JSONDecodeError, AttributeError):
                msg = f"repro evals file is not skill-creator evals.json: {evals_path}"
        if msg:
            (warnings if lesson.get("status") == "DRAFT" else errors).append(msg)
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lessons", nargs="+", type=Path)
    ap.add_argument("--catalog", type=Path, default=REPO / "skills")
    ap.add_argument("--class-map", type=Path, default=CLASS_MAP)
    ap.add_argument("--schema", type=Path, default=SCHEMA)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (testing)")
    args = ap.parse_args(argv)
    try:
        schema = load_schema(args.schema)
        classes = json.loads(args.class_map.read_text(encoding="utf-8"))["classes"]
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": f"setup: {exc}"}))
        return 2
    results, failed = [], False
    for f in args.lessons:
        try:
            lesson = load_doc(f)
            errors, warnings = lint(lesson, args.catalog, classes, schema, today)
        except (OSError, ValueError) as exc:
            lesson, errors, warnings = {}, [f"cannot read lesson: {exc}"], []
        failed |= bool(errors)
        results.append({"file": f.as_posix(), "lesson_id": (lesson or {}).get("lesson_id") if isinstance(lesson, dict) else None,
                        "result": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings})
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
