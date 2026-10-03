#!/usr/bin/env python3
"""Fixture PII scan: no real personal data in test assets (plan §4.13 step 4, ADR 0003).

Scans test directories, fixtures, seeds and .feature Examples tables for values that look like
real personal data. Synthetic data must use reserved values: example.com/.org/.net and *.test /
*.example / *.invalid domains, RFC 5737 IPs, documented PSP test cards and example IBANs, and
555-01xx / Ofcom drama phone numbers.

Detectors and severities:
  EMAIL (block)    address outside reserved domains (and outside --allow-domain)
  PAN (block)      Luhn-valid 13-19 digit card number that is not a documented test card
  IBAN (block)     mod-97-valid IBAN that is not a documented example IBAN
  SSN (block)      valid-format US SSN
  PHONE (warn)     phone number outside the reserved fictional ranges
  PUBLIC_IP (warn) IPv4 outside private, loopback and RFC 5737 ranges
  SECRET_LIKE (info) JWT or API-key-shaped strings; enforcement is deferred to secret scanning
                   (gitleaks, see skills/testing/security-testing/secret-scanning)

There is deliberately NO inline suppression comment. An agent could add one to bypass the scan.
Exceptions come only from --allowlist FILE (JSON list of exact values), which lives in a reviewed path.

Usage: fixture_pii_scan.py [PATH ...] [--all-files] [--allow-domain D ...] [--allowlist FILE]
Exit: 0 = no blocking findings, 1 = blocking findings, 2 = bad input.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".dart_tool"}
TEXT_EXT = {".json", ".yaml", ".yml", ".csv", ".tsv", ".sql", ".feature", ".txt", ".xml", ".ts", ".tsx", ".js",
            ".jsx", ".mjs", ".py", ".java", ".kt", ".dart", ".cs", ".go", ".rb", ".swift", ".properties", ".env", ".ndjson"}
TEST_ASSET_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec|e2e|integration_test|androidTest|src/test|features|fixtures|__fixtures__|"
    r"factories|builders|testdata|test-data|test_data|seeds?|mocks|__mocks__)/|\.(spec|test|cy)\.[cm]?[jt]sx?$|"
    r"_test\.(dart|py|go)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs|swift)$|\.feature$|\.fixtures?\.")

RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")
TEST_CARDS = {
    "4242424242424242", "4000056655665556", "4000002500003155", "4000000000003220", "4000000000000002",
    "4000000000009995", "5555555555554444", "2223003122003222", "5200828282828210", "5105105105105100",
    "378282246310005", "371449635398431", "6011111111111117", "6011000990139424", "3056930009020004",
    "36227206271667", "3566002020360505", "6200000000000005", "4111111111111111", "4012888888881881",
    "4000000000000077", "5454545454545454", "4917610000000000", "4988438843884305", "374245455400126",
    "6011601160116611", "3600666633336666", "5500000000000004", "4444333322221111", "4012888888881881",
}
EXAMPLE_IBANS = {
    "DE89370400440532013000", "GB82WEST12345698765432", "GB33BUKB20201555555555",
    "FR1420041010050500013M02606", "NL91ABNA0417164300", "ES9121000418450200051332",
    "IT60X0542811101000000123456", "BE68539007547034", "CH9300762011623852957",
}

EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
SSN = re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])")
PHONE = re.compile(r"(?<![\w+])(\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\d])|(?<![\w])\+\d{10,14}(?!\d)")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
SECRET_LIKE = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|AKIA[0-9A-Z]{16}|sk_live_[A-Za-z0-9]{10,}"
    r"|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}")
FICTIONAL_PHONE = re.compile(r"555[\s.-]?01\d\d$|7700[\s.-]?900\d{3}$|20[\s.-]?7946[\s.-]?0\d{3}$")


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def iban_ok(iban: str) -> bool:
    s = iban[4:] + iban[:4]
    num = "".join(str(int(c, 36)) for c in s)
    return int(num) % 97 == 1


def domain_reserved(domain: str, extra: set[str]) -> bool:
    d = domain.lower().rstrip(".")
    return (d in extra or any(d == r or d.endswith("." + r) for r in RESERVED_DOMAINS)
            or d.endswith(RESERVED_TLDS) or any(d == e or d.endswith("." + e) for e in extra))


def ip_allowed(ip: str) -> bool:
    try:
        a = ipaddress.IPv4Address(ip)
    except ValueError:
        return True  # not an IP (e.g. version 999.1.1.1)
    if a.is_private or a.is_loopback or a.is_unspecified or a.is_link_local or a.is_multicast or a.is_reserved:
        return True
    return any(a in ipaddress.IPv4Network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))


def scan_text(rel: str, text: str, allow_domains: set[str], allowlist: set[str]) -> list[dict]:
    findings = []

    def add(kind, severity, lineno, value, why):
        if value in allowlist:
            return
        masked = value if severity == "info" else (value[:2] + "…" + value[-2:] if len(value) > 6 else "…")
        findings.append({"type": kind, "severity": severity, "file": rel, "line": lineno,
                         "value_masked": masked, "why": why})

    for lineno, line in enumerate(text.splitlines(), 1):
        for m in EMAIL.finditer(line):
            if not domain_reserved(m.group(1), allow_domains):
                add("EMAIL", "block", lineno, m.group(0),
                    f"domain '{m.group(1)}' is not reserved; use example.com / *.test")
        for m in PAN.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and luhn_ok(digits) and digits not in TEST_CARDS and len(set(digits)) > 1:
                add("PAN", "block", lineno, digits, "Luhn-valid card number that is not a documented test card")
        for m in IBAN.finditer(line):
            iban = m.group(0).replace(" ", "")
            if 15 <= len(iban) <= 34 and iban not in EXAMPLE_IBANS:
                try:
                    if iban_ok(iban):
                        add("IBAN", "block", lineno, iban, "checksum-valid IBAN that is not a documented example IBAN")
                except ValueError:
                    pass
        for m in SSN.finditer(line):
            add("SSN", "block", lineno, m.group(0), "valid-format US SSN")
        for m in PHONE.finditer(line):
            raw = m.group(0)
            if not FICTIONAL_PHONE.search(re.sub(r"[()]", "", raw).strip()):
                add("PHONE", "warn", lineno, raw, "phone number outside 555-01xx / Ofcom drama ranges")
        for m in IPV4.finditer(line):
            if not ip_allowed(m.group(1)):
                add("PUBLIC_IP", "warn", lineno, m.group(1), "public IPv4; use RFC 5737 (192.0.2.0/24 etc.)")
        for m in SECRET_LIKE.finditer(line):
            findings.append({"type": "SECRET_LIKE", "severity": "info", "file": rel, "line": lineno,
                             "value_masked": m.group(0)[:6] + "…",
                             "why": "secret-shaped string; enforced by secret scanning (gitleaks), not this check"})
    return findings


def iter_targets(paths: list[Path], all_files: bool):
    for base in paths:
        if base.is_file():
            yield base, base.name
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or set(p.relative_to(base).parts) & SKIP_DIRS:
                continue
            rel = p.relative_to(base).as_posix()
            if p.suffix.lower() not in TEXT_EXT and p.name != ".env":
                continue
            if all_files or TEST_ASSET_PATH.search(rel):
                yield p, rel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--all-files", action="store_true", help="scan every text file, not only test assets")
    ap.add_argument("--allow-domain", nargs="*", default=[])
    ap.add_argument("--allowlist", help="JSON list of exact values to ignore (reviewed path)")
    args = ap.parse_args(argv)
    try:
        allowlist = set(json.loads(Path(args.allowlist).read_text(encoding="utf-8"))) if args.allowlist else set()
        paths = [Path(p) for p in args.paths]
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            raise ValueError(f"paths not found: {missing}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    findings, scanned = [], 0
    for p, rel in iter_targets(paths, args.all_files):
        scanned += 1
        findings.extend(scan_text(rel, p.read_text(encoding="utf-8", errors="replace"),
                                  {d.lower() for d in args.allow_domain}, allowlist))
    blocking = [f for f in findings if f["severity"] == "block"]
    print(json.dumps({"classification": "FACT", "source": "fixture_pii_scan.py", "files_scanned": scanned,
                      "findings": findings,
                      "summary": {"blocking": len(blocking),
                                  "warnings": sum(1 for f in findings if f["severity"] == "warn"),
                                  "info": sum(1 for f in findings if f["severity"] == "info")},
                      "verdict": "FAIL" if blocking else "PASS"}, indent=2, ensure_ascii=False))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
