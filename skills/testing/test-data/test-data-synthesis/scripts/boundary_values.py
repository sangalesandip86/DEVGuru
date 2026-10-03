#!/usr/bin/env python3
"""Deterministic boundary-value / equivalence-partition case generator (plan §4.13 step 4).

The agent (qa-derive) chooses the partitions and the specified limits; this tool generates the
VALUES, so fixtures are reproducible and nobody "imagines" boundary data.

Input (JSON file or stdin):
    {
      "entity": "Transfer",
      "seed": 42,                                   # optional, default 0
      "fields": {
        "amount":   {"type": "number", "min": 0.01, "max": 10000, "precision": 2, "required": true},
        "currency": {"type": "enum", "enum": ["EUR", "USD"], "required": true},
        "memo":     {"type": "string", "min_length": 0, "max_length": 140, "nullable": true},
        "iban":     {"type": "string", "pattern": "^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$",
                     "examples_valid": ["DE89370400440532013000"]},
        "count":    {"type": "integer", "min": 1, "max": 10},
        "date":     {"type": "date", "min": "2024-01-01", "max": "2024-12-31"},
        "tags":     {"type": "array", "min_items": 0, "max_items": 5, "items": {"type": "string", "max_length": 10}},
        "urgent":   {"type": "boolean"}
      }
    }

Every case carries an `expect` label:
    valid        - the spec says this must be accepted
    invalid      - the spec says this must be rejected
    unspecified  - the spec is silent (whitespace-only, case variants, ...). The tool never invents
                   an expectation: qa-derive resolves it from the AC or raises a QUESTION.

Output: per-field cases plus three one-factor-at-a-time datasets (happy, boundary, negative),
the seed, and `questions[]` for anything the tool could not generate (for example a regex
pattern without examples).

Usage: boundary_values.py [spec.json] [--seed N]       Exit: 0 ok, 2 bad input.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import string
import sys
from decimal import Decimal
from pathlib import Path

SENTINEL_MISSING = "<<MISSING>>"   # serialised marker meaning "omit this field from the payload"


def _case(value, expect: str, technique: str, why: str) -> dict:
    return {"value": value, "expect": expect, "technique": technique, "why": why}


def _filler(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.ascii_letters) for _ in range(max(n, 0)))


def gen_integer(spec: dict, rng: random.Random) -> list[dict]:
    lo, hi = spec.get("min"), spec.get("max")
    cases = []
    if lo is not None:
        cases += [_case(lo - 1, "invalid", "BVA", "min-1"), _case(lo, "valid", "BVA", "min"),
                  _case(lo + 1, "valid", "BVA", "min+1")]
    if hi is not None:
        cases += [_case(hi - 1, "valid", "BVA", "max-1"), _case(hi, "valid", "BVA", "max"),
                  _case(hi + 1, "invalid", "BVA", "max+1")]
    if lo is not None and hi is not None:
        cases.append(_case((lo + hi) // 2, "valid", "EP", "nominal (midpoint)"))
    if lo is None:
        cases += [_case(-1, "unspecified", "EP", "negative; no min specified"),
                  _case(0, "unspecified", "EP", "zero; no min specified")]
    if hi is None:
        cases.append(_case(2**31, "unspecified", "EP", "beyond int32; no max specified"))
    cases.append(_case("1.5", "invalid", "EP", "non-integer type"))
    return _dedupe(cases)


def gen_number(spec: dict, rng: random.Random) -> list[dict]:
    precision = spec.get("precision")
    step = Decimal(str(spec["step"])) if "step" in spec else (
        Decimal(1).scaleb(-int(precision)) if precision is not None else None)
    lo = Decimal(str(spec["min"])) if spec.get("min") is not None else None
    hi = Decimal(str(spec["max"])) if spec.get("max") is not None else None
    eps = step if step is not None else Decimal("0.01")
    note = "" if step is not None else " (step assumed 0.01; state precision in the spec)"

    def num(d: Decimal):
        return float(d)

    cases = []
    if lo is not None:
        cases += [_case(num(lo - eps), "invalid", "BVA", "min-step" + note), _case(num(lo), "valid", "BVA", "min"),
                  _case(num(lo + eps), "valid", "BVA", "min+step" + note)]
    if hi is not None:
        cases += [_case(num(hi - eps), "valid", "BVA", "max-step" + note), _case(num(hi), "valid", "BVA", "max"),
                  _case(num(hi + eps), "invalid", "BVA", "max+step" + note)]
    if lo is not None and hi is not None:
        mid = ((lo + hi) / 2).quantize(eps) if step is not None else (lo + hi) / 2
        cases.append(_case(num(mid), "valid", "EP", "nominal (midpoint)"))
    if precision is not None:
        base = lo if lo is not None else Decimal(1)
        cases.append(_case(str(base + Decimal(1).scaleb(-(int(precision) + 1))), "invalid", "BVA",
                           f"more than {precision} decimal places"))
    if lo is None:
        cases.append(_case(0, "unspecified", "EP", "zero; no min specified"))
        cases.append(_case(-1, "unspecified", "EP", "negative; no min specified"))
    cases.append(_case("NaN", "invalid", "EP", "not a number"))
    return _dedupe(cases)


def gen_string(spec: dict, rng: random.Random, questions: list, field: str) -> list[dict]:
    lo, hi = spec.get("min_length"), spec.get("max_length")
    pattern = spec.get("pattern")
    valid_examples = spec.get("examples_valid") or []
    invalid_examples = spec.get("examples_invalid") or []
    cases = []
    if pattern and not valid_examples:
        questions.append({
            "field": field,
            "question": f"Field '{field}' has pattern {pattern!r} but no examples_valid; the tool does not "
                        "invent values matching arbitrary regexes. Provide 1-3 valid examples (synthetic, "
                        "reserved values only) or approve qa-derive drafting them.",
        })
    for ex in valid_examples:
        cases.append(_case(ex, "valid", "EP", "provided valid example (pattern)"))
    for ex in invalid_examples:
        cases.append(_case(ex, "invalid", "EP", "provided invalid example (pattern)"))
    if pattern:
        cases.append(_case("!!", "invalid", "EP", "violates pattern (punctuation only)"))
    if not pattern:
        if lo is not None:
            if lo > 0:
                cases.append(_case(_filler(rng, lo - 1), "invalid", "BVA", "min_length-1"))
            cases += [_case(_filler(rng, lo), "valid", "BVA", "min_length"),
                      _case(_filler(rng, lo + 1), "valid", "BVA", "min_length+1")]
        if hi is not None:
            cases += [_case(_filler(rng, hi - 1), "valid", "BVA", "max_length-1"),
                      _case(_filler(rng, hi), "valid", "BVA", "max_length"),
                      _case(_filler(rng, hi + 1), "invalid", "BVA", "max_length+1")]
            if hi >= 1:
                cases.append(_case("é" * hi, "valid", "BVA",
                                   "max_length in multi-byte chars (catches byte-vs-char length bugs)"))
        if lo is None or lo == 0:
            cases.append(_case("", "valid" if lo == 0 else "unspecified", "BVA", "empty string"))
        nominal_len = (lo or 1) if hi is None else max(lo or 1, min(hi, 8))
        cases.append(_case(_filler(rng, nominal_len), "valid", "EP", "nominal"))
        cases += [_case("   ", "unspecified", "error-guessing", "whitespace only"),
                  _case(" a ", "unspecified", "error-guessing", "leading/trailing whitespace"),
                  _case("Robert'); DROP TABLE x;--", "unspecified", "error-guessing",
                        "SQL metacharacters (must be stored/echoed verbatim or rejected, never executed)"),
                  _case("<script>alert(1)</script>", "unspecified", "error-guessing",
                        "markup (must be escaped on output)"),
                  _case("‮RTL​", "unspecified", "error-guessing", "bidi/zero-width characters")]
    return _dedupe(cases)


def gen_enum(spec: dict, rng: random.Random) -> list[dict]:
    members = spec.get("enum") or []
    cases = [_case(m, "valid", "EP", "enum member") for m in members]
    cases.append(_case("__NOT_A_MEMBER__", "invalid", "EP", "not in enum"))
    if members and isinstance(members[0], str) and members[0].lower() != members[0]:
        cases.append(_case(members[0].lower(), "unspecified", "error-guessing", "case variant of a member"))
    return cases


def gen_boolean(spec: dict, rng: random.Random) -> list[dict]:
    return [_case(True, "valid", "EP", "true"), _case(False, "valid", "EP", "false"),
            _case("yes", "invalid", "EP", "truthy string, not boolean")]


def gen_date(spec: dict, rng: random.Random) -> list[dict]:
    lo = dt.date.fromisoformat(spec["min"]) if spec.get("min") else None
    hi = dt.date.fromisoformat(spec["max"]) if spec.get("max") else None
    day = dt.timedelta(days=1)
    cases = []
    if lo:
        cases += [_case((lo - day).isoformat(), "invalid", "BVA", "min-1 day"),
                  _case(lo.isoformat(), "valid", "BVA", "min"),
                  _case((lo + day).isoformat(), "valid", "BVA", "min+1 day")]
    if hi:
        cases += [_case((hi - day).isoformat(), "valid", "BVA", "max-1 day"),
                  _case(hi.isoformat(), "valid", "BVA", "max"),
                  _case((hi + day).isoformat(), "invalid", "BVA", "max+1 day")]
    if lo and hi:
        cases.append(_case((lo + (hi - lo) / 2).isoformat(), "valid", "EP", "nominal (midpoint)"))
    cases += [_case("2024-02-30", "invalid", "EP", "impossible calendar date"),
              _case("2024-02-29", "unspecified" if not (lo and hi) else
                    ("valid" if lo <= dt.date(2024, 2, 29) <= hi else "invalid"), "BVA", "leap day"),
              _case("31/12/2024", "invalid", "EP", "wrong format (non-ISO)")]
    return _dedupe(cases)


def gen_array(spec: dict, rng: random.Random, questions: list, field: str) -> list[dict]:
    lo, hi = spec.get("min_items"), spec.get("max_items")
    item = _nominal(spec.get("items") or {"type": "string"}, rng, questions, field + "[]")
    cases = []
    if lo is not None:
        if lo > 0:
            cases.append(_case([item] * (lo - 1), "invalid", "BVA", "min_items-1"))
        cases.append(_case([item] * lo, "valid", "BVA", "min_items"))
    if hi is not None:
        cases += [_case([item] * hi, "valid", "BVA", "max_items"),
                  _case([item] * (hi + 1), "invalid", "BVA", "max_items+1")]
    if lo is None:
        cases.append(_case([], "unspecified", "BVA", "empty collection; no min_items specified"))
    if spec.get("unique_items"):
        cases.append(_case([item, item], "invalid", "EP", "duplicate items"))
    return _dedupe(cases)


GENERATORS = {"integer": gen_integer, "number": gen_number, "enum": gen_enum,
              "boolean": gen_boolean, "date": gen_date}


def field_cases(name: str, spec: dict, rng: random.Random, questions: list) -> list[dict]:
    t = spec.get("type")
    if t == "string":
        cases = gen_string(spec, rng, questions, name)
    elif t == "array":
        cases = gen_array(spec, rng, questions, name)
    elif t in GENERATORS:
        cases = GENERATORS[t](spec, rng)
    else:
        raise ValueError(f"field '{name}': unsupported type {t!r}")
    required = spec.get("required", False)
    cases.append(_case(SENTINEL_MISSING, "invalid" if required else "valid", "EP",
                       "field omitted" + (" (required)" if required else " (optional)")))
    nullable = spec.get("nullable")
    if nullable is None:
        cases.append(_case(None, "unspecified", "EP", "null; nullability not specified"))
    else:
        cases.append(_case(None, "valid" if nullable else "invalid", "EP", "null"))
    return cases


def _nominal(spec: dict, rng: random.Random, questions: list, name: str):
    """A single valid, unremarkable value used as the baseline in datasets."""
    probe = field_cases(name, spec, random.Random(rng.random()), [])
    for c in probe:
        if c["expect"] == "valid" and c["technique"] == "EP" and c["value"] not in (None, SENTINEL_MISSING):
            return c["value"]
    for c in probe:
        if c["expect"] == "valid" and c["value"] not in (None, SENTINEL_MISSING):
            return c["value"]
    questions.append({"field": name, "question": f"No valid nominal value could be generated for '{name}'."})
    return None


def _dedupe(cases: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in cases:
        key = json.dumps([c["value"], c["expect"]], sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _record(base: dict, field: str, value) -> dict:
    rec = dict(base)
    if value == SENTINEL_MISSING:
        rec.pop(field, None)
    else:
        rec[field] = value
    return rec


def generate(spec: dict, seed: int | None = None) -> dict:
    seed = spec.get("seed", 0) if seed is None else seed
    rng = random.Random(seed)
    fields = spec.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise ValueError("spec.fields must be a non-empty object")
    questions: list = []
    per_field = {name: field_cases(name, fs, rng, questions) for name, fs in fields.items()}
    happy = {}
    for name, fs in fields.items():
        val = _nominal(fs, rng, questions, name)
        if val is not None:
            happy[name] = val
    boundary, negative, unspecified = [], [], []
    for name, cases in per_field.items():
        for i, c in enumerate(cases):
            rec = {"id": f"{name}#{i + 1}", "varies": name, "why": c["why"], "technique": c["technique"],
                   "expect": c["expect"], "payload": _record(happy, name, c["value"])}
            if c["expect"] == "invalid":
                negative.append(rec)
            elif c["expect"] == "valid":
                # valid boundaries AND every other valid partition (enum members, optional omitted, ...)
                boundary.append(rec)
            elif c["expect"] == "unspecified":
                unspecified.append(rec)
    for rec in unspecified:
        questions.append({"field": rec["varies"],
                          "question": f"Expected outcome for {rec['varies']} = {rec['payload'].get(rec['varies'], 'omitted')!r} "
                                      f"({rec['why']}) is not specified. Resolve from AC or raise to product-owner."})
    return {
        "classification": "FACT",
        "source": "boundary_values.py",
        "entity": spec.get("entity"),
        "seed": seed,
        "fields": per_field,
        "datasets": {"happy": [{"id": "happy#1", "expect": "valid", "payload": happy}],
                     "boundary": boundary, "negative": negative, "unspecified": unspecified},
        "questions": questions,
        "missing_marker": SENTINEL_MISSING,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", nargs="?", help="spec JSON file (default: stdin)")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args(argv)
    try:
        raw = Path(args.spec).read_text(encoding="utf-8") if args.spec else sys.stdin.read()
        result = generate(json.loads(raw), args.seed)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
