#!/usr/bin/env python3
"""Test integrity guard: detects test weakening in a diff (plan §4.13 rule 6, ADR 0003).

An agent cannot make a red build green by weakening the tests. This check flags:
  TEST_FILE_DELETED, TEST_REMOVED, TEST_RENAMED_OR_REPLACED, ASSERTION_REMOVED,
  EXPECTATION_CHANGED, EXAMPLE_ROWS_REMOVED, SKIP_ADDED, FOCUS_ADDED,
  TIMEOUT_OR_TOLERANCE_LOOSENED, SNAPSHOT_MASS_UPDATE, NO_ASSERTIONS, SUT_MOCKED,
  SWALLOWED_ASSERTION

The core rule: an existing expectation may change only when the linked story's AC changed.
EXPECTATION_CHANGED, ASSERTION_REMOVED and EXAMPLE_ROWS_REMOVED are marked `ac-covered` (not
blocking) when every AC tag (ST-n/AC-n) on the affected test appears in --ac-changed. An
untagged test can never be ac-covered.

Inputs (one of):
  --diff FILE            unified diff (git diff output); add --head-root DIR for test-level
                         AC lookup (otherwise tags are read from the diff text of the file)
  --base DIR --head DIR  two checkouts; the diff is computed for test, snapshot and feature files

Options:
  --ac-changed IDS       comma-separated AC IDs whose hash changed (from plan-lint / ledger)
  --ac-changed-file F    the same, as a JSON list
  --snapshot-threshold N max changed snapshot files before SNAPSHOT_MASS_UPDATE (default 5)
  --overrides FILE       JSON [{finding_id, ledger_entry}] -- REVIEWED acceptances (qa-diagnose,
                         or a human at HIGH/CRITICAL); matching findings become `accepted`

Output: JSON findings on stdout (classification FACT).
Exit: 0 = no open blocking findings, 1 = open blocking findings, 2 = bad input.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TEST_PATH = re.compile(
    r"(\.(spec|test|cy)\.[cm]?[jt]sx?$|_test\.(dart|py|go)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs|swift)$"
    r"|_spec\.rb$|\.feature$|(^|/)(tests?|__tests__|spec|e2e|integration_test|androidTest|src/test)/)")
SNAPSHOT_PATH = re.compile(r"(__snapshots__/|\.snap$|/goldens?/|-snapshots/|\.golden$)")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".dart_tool"}

TEST_DECL = [
    re.compile(r"\b(?:it|test|specify)(?:\.\w+)?\s*\(\s*(['\"`])(?P<name>.+?)\1"),
    re.compile(r"\b(?:testWidgets|blocTest(?:<[^>]*>)?|patrolTest)\s*\(\s*(['\"])(?P<name>.+?)\1"),
    re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>test_\w+)\s*\("),
    re.compile(r"^\s*func\s+(?P<name>Test\w+)\s*\("),
    re.compile(r"^\s*func\s+(?P<name>test\w+)\s*\("),
    re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest)\b(?P<name>)"),
    re.compile(r"\[(?:Fact|Theory|Test|TestMethod|TestCase)\b(?P<name>)"),
    re.compile(r"^\s*Scenario(?: Outline)?:\s*(?P<name>.+)$"),
    re.compile(r"^\s*it\s+(['\"])(?P<name>.+?)\1"),
]
ASSERTION = re.compile(
    r"\bexpect\s*\(|\bexpectLater\s*\(|\bassert\w*\b|\.should\b|\bshould\s*\(|\bverify\s*\(|XCTAssert\w*"
    r"|\bAssert\.\w+|\brequire\.\w+\(|\bt\.(?:Error|Errorf|Fatal|Fatalf)\(|\bassertThat\b|^\s*Then\b|^\s*And\b.*\bshould\b")
SKIP_ADDED = re.compile(
    r"\b(?:describe|it|test|context|suite)\.(?:skip|todo|fixme)\b|\bx(?:it|describe|test|context)\s*\("
    r"|\btest\.fixme\b|@Disabled\b|@Ignore\b|pytest\.mark\.(?:skip|skipif|xfail)|@unittest\.(?:skip|expectedFailure)"
    r"|\bskip\s*:\s*(?:true|['\"])|\bt\.Skip(?:f|Now)?\(|\[Ignore\]|Skip\s*=\s*\"|@wip\b|@skip\b|@ignore\b")
FOCUS_ADDED = re.compile(r"\b(?:describe|it|test|context)\.only\b|\bf(?:it|describe)\s*\(|\bsolo\s*:\s*true")
LOOSEN_KEY = re.compile(r"timeout|tolerance|delta|epsilon|closeTo|toBeCloseTo|approx|rel_tol|abs_tol|retries|retry|slowMo|threshold|maxDiffPixel", re.I)
SWALLOW = re.compile(
    r"except\s*:\s*(?:pass)?\s*$|except\s+(?:AssertionError|Exception|BaseException)\b"
    r"|catch\s*\(\s*(?:e|err|error|_|ex)?\s*(?::\s*\w+)?\s*\)\s*\{\s*\}|catch\s*\{\s*\}"
    r"|\.catch\(\s*\(\s*\w*\s*\)\s*=>\s*(?:\{\s*\}|null|undefined)\s*\)"
    r"|catch\s*\(\s*(?:AssertionError|AssertionFailedError|Throwable)\b|on\s+TestFailure\b|catch\s*\(\s*_\s*\)\s*\{\s*\}")
AC_TAG = re.compile(r"ST-\d+/AC-\d+")
LITERAL_STR = re.compile(r"(['\"`])(?:\\.|(?!\1).)*\1")
LITERAL_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
MOCK_CALL = re.compile(
    r"\b(?:jest|vi)\.mock\(\s*['\"](?P<js>[^'\"]+)['\"]|\bmock\(\s*(?P<java>\w+)\.class|\bmockk<(?P<kt>\w+)>"
    r"|class\s+Mock(?P<dart>\w+)\s+extends\s+Mock|patch\.object\(\s*(?P<py>\w+)\b|\bnew\s+Mock<(?P<cs>\w+)>")


@dataclass
class FileDiff:
    path: str
    old_path: str | None
    new_path: str | None
    hunks: list = field(default_factory=list)   # [(new_start, [(tag, text, new_lineno|None)])]

    @property
    def deleted(self) -> bool:
        return self.new_path is None

    @property
    def added_file(self) -> bool:
        return self.old_path is None


def parse_unified_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_path = new_path = None
    new_no = 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            cur = None
            old_path = new_path = None
            continue
        if raw.startswith("--- "):
            p = raw[4:].strip().split("\t")[0]
            old_path = None if p == "/dev/null" else re.sub(r"^a/", "", p)
            continue
        if raw.startswith("+++ "):
            p = raw[4:].strip().split("\t")[0]
            new_path = None if p == "/dev/null" else re.sub(r"^b/", "", p)
            cur = FileDiff(path=new_path or old_path or "", old_path=old_path, new_path=new_path)
            files.append(cur)
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if m and cur is not None:
            new_no = int(m.group(1))
            cur.hunks.append((new_no, []))
            continue
        if cur is None or not cur.hunks:
            continue
        lines = cur.hunks[-1][1]
        if raw.startswith("+"):
            lines.append(("+", raw[1:], new_no))
            new_no += 1
        elif raw.startswith("-"):
            lines.append(("-", raw[1:], None))
        elif raw.startswith(" ") or raw == "":
            lines.append((" ", raw[1:] if raw else "", new_no))
            new_no += 1
    return files


def diff_dirs(base: Path, head: Path) -> str:
    def collect(root: Path) -> dict[str, Path]:
        out = {}
        if not root.exists():
            return out
        for p in root.rglob("*"):
            if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
                rel = p.relative_to(root).as_posix()
                if TEST_PATH.search(rel) or SNAPSHOT_PATH.search(rel):
                    out[rel] = p
        return out

    b, h = collect(base), collect(head)
    chunks = []
    for rel in sorted(set(b) | set(h)):
        bt = b[rel].read_text(encoding="utf-8", errors="replace").splitlines() if rel in b else []
        ht = h[rel].read_text(encoding="utf-8", errors="replace").splitlines() if rel in h else []
        if bt == ht:
            continue
        a_name = f"a/{rel}" if rel in b else "/dev/null"
        b_name = f"b/{rel}" if rel in h else "/dev/null"
        chunks.append(f"diff --git a/{rel} b/{rel}")
        chunks.extend(difflib.unified_diff(bt, ht, a_name, b_name, n=3, lineterm=""))
    return "\n".join(chunks)


def skeleton(line: str) -> str:
    s = LITERAL_STR.sub("S", line)
    s = LITERAL_NUM.sub("N", s)
    return re.sub(r"\s+", " ", s).strip()


def numbers(line: str) -> list[float]:
    return [float(x) for x in LITERAL_NUM.findall(LITERAL_STR.sub("S", line))]


def decl_name(line: str) -> str | None:
    for rx in TEST_DECL:
        m = rx.search(line)
        if m:
            return (m.group("name") or line.strip())[:120]
    return None


def subject_of(path: str) -> str:
    stem = Path(path).name
    stem = re.sub(r"\.(spec|test|cy)\.[cm]?[jt]sx?$|_test\.(dart|py|go)$|Tests?\.(java|kt|cs|swift)$|\.[a-z]+$", "", stem)
    stem = re.sub(r"^test_", "", stem)
    return stem


def norm_ident(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class Guard:
    def __init__(self, ac_changed: set[str], head_root: Path | None, snapshot_threshold: int):
        self.ac_changed = ac_changed
        self.head_root = head_root
        self.snapshot_threshold = snapshot_threshold
        self.findings: list[dict] = []
        self._head_cache: dict[str, list[str] | None] = {}

    def add(self, ftype: str, severity: str, path: str, line, detail: str, ac_tags=None, ac_rule=False):
        status = "open"
        if ac_rule:
            if ac_tags and set(ac_tags) <= self.ac_changed:
                status = "ac-covered"
                detail += f" (AC changed: {', '.join(sorted(ac_tags))})"
            elif not ac_tags:
                detail += " (test carries no ST-n/AC-n tag, so it cannot be AC-covered)"
            else:
                detail += f" (AC tags {', '.join(sorted(ac_tags))} unchanged)"
        self.findings.append({
            "id": f"{ftype}:{path}:{line if line is not None else '-'}",
            "type": ftype, "severity": severity, "file": path, "line": line,
            "detail": detail, "ac_tags": sorted(ac_tags or []), "status": status,
        })

    def head_lines(self, path: str) -> list[str] | None:
        if self.head_root is None:
            return None
        if path not in self._head_cache:
            p = self.head_root / path
            self._head_cache[path] = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else None
        return self._head_cache[path]

    def tags_for(self, fd: FileDiff, new_lineno: int | None) -> list[str]:
        """AC tags of the test enclosing new_lineno (head file) or, failing that, of the whole file diff."""
        lines = self.head_lines(fd.path)
        if lines is not None and new_lineno:
            i = min(new_lineno - 1, len(lines) - 1)
            while i >= 0:
                if decl_name(lines[i]) is not None:
                    window = lines[max(0, i - 3): i + 1]
                    return sorted({t for l in window for t in AC_TAG.findall(l)})
                i -= 1
            return []
        text = "\n".join(t for _, hunk in fd.hunks for _, t, _ in hunk)
        return sorted(set(AC_TAG.findall(text)))

    def check_file(self, fd: FileDiff):
        path = fd.path
        is_feature = path.endswith(".feature")
        if fd.deleted:
            removed_tests = [decl_name(t) for _, h in fd.hunks for tag, t, _ in h if tag == "-" and decl_name(t)]
            self.add("TEST_FILE_DELETED", "block", path, None,
                     f"test file deleted ({len(removed_tests)} test declarations)")
            return
        removed_decls, added_decls = [], []
        for _, hunk in fd.hunks:
            removed = [(t) for tag, t, _ in hunk if tag == "-"]
            added = [(t, n) for tag, t, n in hunk if tag == "+"]
            for t in removed:
                name = decl_name(t)
                if name is not None:
                    removed_decls.append(name)
            for t, n in added:
                name = decl_name(t)
                if name is not None:
                    added_decls.append((name, n))
                if SKIP_ADDED.search(t):
                    self.add("SKIP_ADDED", "block", path, n, f"skip/disable marker added: {t.strip()[:100]}")
                if FOCUS_ADDED.search(t):
                    self.add("FOCUS_ADDED", "block", path, n, f"focus marker added (silently skips the rest): {t.strip()[:100]}")
                if SWALLOW.search(t):
                    self.add("SWALLOWED_ASSERTION", "block", path, n, f"failure-swallowing handler added: {t.strip()[:100]}")
                self.check_mock(path, t, n)

            # pair removed/added lines by skeleton
            rem_assert = [t for t in removed if ASSERTION.search(t) or LOOSEN_KEY.search(t)]
            add_pool = [(t, n) for t, n in added]
            unpaired_removed = []
            for r in rem_assert:
                sk = skeleton(r)
                match = next((a for a in add_pool if skeleton(a[0]) == sk and a[0].strip() != r.strip()), None)
                if match is None:
                    if any(a[0].strip() == r.strip() for a in add_pool):
                        continue  # moved, unchanged
                    if ASSERTION.search(r):
                        unpaired_removed.append(r)
                    continue
                add_pool.remove(match)
                a_text, a_no = match
                if LOOSEN_KEY.search(r):
                    old_n, new_n = numbers(r), numbers(a_text)
                    if len(old_n) == len(new_n) and any(n > o for o, n in zip(old_n, new_n)):
                        self.add("TIMEOUT_OR_TOLERANCE_LOOSENED", "block", path, a_no,
                                 f"{r.strip()[:80]}  ->  {a_text.strip()[:80]}")
                        continue
                if ASSERTION.search(r):
                    self.add("EXPECTATION_CHANGED", "block", path, a_no,
                             f"{r.strip()[:80]}  ->  {a_text.strip()[:80]}",
                             ac_tags=self.tags_for(fd, a_no), ac_rule=True)
            # Remaining removed assertions that were *replaced* by a differently-shaped assertion in the
            # same hunk (e.g. toThrow() -> not.toThrow()) are expectation changes too; pair them in order.
            leftover_added = [(t, n) for t, n in add_pool
                              if ASSERTION.search(t) and not any(t.strip() == r.strip() for r in removed)
                              and decl_name(t) is None]
            replaced = list(zip(unpaired_removed, leftover_added))
            for r, (a_text, a_no) in replaced:
                self.add("EXPECTATION_CHANGED", "block", path, a_no,
                         f"{r.strip()[:80]}  ->  {a_text.strip()[:80]}",
                         ac_tags=self.tags_for(fd, a_no), ac_rule=True)
            truly_removed = unpaired_removed[len(replaced):]
            if truly_removed:
                anchor = next((n for _, _, n in hunk if n), None)
                self.add("ASSERTION_REMOVED", "block", path, anchor,
                         f"{len(truly_removed)} assertion line(s) removed without replacement, e.g. {truly_removed[0].strip()[:80]}",
                         ac_tags=self.tags_for(fd, anchor), ac_rule=True)
            if is_feature:
                rows_removed = sum(1 for t in removed if t.strip().startswith("|"))
                rows_added = sum(1 for tag, t, _n in hunk if tag == "+" and t.strip().startswith("|"))
                if rows_removed > rows_added:
                    anchor = next((n for _, _, n in hunk if n), None)
                    self.add("EXAMPLE_ROWS_REMOVED", "block", path, anchor,
                             f"{rows_removed - rows_added} Examples/data-table row(s) removed",
                             ac_tags=self.tags_for(fd, anchor), ac_rule=True)

        added_names = {n for n, _ in added_decls}
        gone = [n for n in removed_decls if n not in added_names]
        if gone:
            if len(added_decls) >= len(removed_decls):
                self.add("TEST_RENAMED_OR_REPLACED", "warn", path, None,
                         f"test declaration(s) no longer present under the same name: {gone[:5]}")
            else:
                self.add("TEST_REMOVED", "block", path, None,
                         f"{len(removed_decls) - len(added_decls)} net test declaration(s) removed: {gone[:5]}")

        # new tests with no assertions
        for name, n in added_decls:
            if name in set(removed_decls) or is_feature:
                continue
            body = self.body_after(fd, n)
            if body is not None and not any(ASSERTION.search(l) for l in body):
                self.add("NO_ASSERTIONS", "block", path, n, f"new test '{name}' contains no assertion")

    def body_after(self, fd: FileDiff, decl_no: int | None) -> list[str] | None:
        lines = self.head_lines(fd.path)
        if lines is not None and decl_no:
            body = []
            for l in lines[decl_no:]:
                if decl_name(l) is not None:
                    break
                body.append(l)
            return [lines[decl_no - 1]] + body
        for _, hunk in fd.hunks:
            nos = [n for _, _, n in hunk]
            if decl_no in nos:
                start = nos.index(decl_no)
                body = [hunk[start][1]]
                for tag, t, _ in hunk[start + 1:]:
                    if tag == "-":
                        continue
                    if decl_name(t) is not None:
                        return body
                    body.append(t)
                # hunk ended before the next declaration: body incomplete -> unknown
                return body if any(ASSERTION.search(l) for l in body) else None
        return None

    def check_mock(self, path: str, line: str, n):
        m = MOCK_CALL.search(line)
        if not m:
            return
        subject = norm_ident(subject_of(path))
        if not subject:
            return
        target = next(g for g in m.groups() if g)
        if m.group("js"):
            target = re.sub(r"\.[cm]?[jt]sx?$", "", target.rstrip("/").split("/")[-1])
        target_name = norm_ident(target)
        if target_name == subject:
            self.add("SUT_MOCKED", "warn", path, n,
                     f"the module/class under test appears to be mocked ({target}); the test may assert on the mock")

    def run(self, files: list[FileDiff]) -> dict:
        snapshot_files = [f.path for f in files if SNAPSHOT_PATH.search(f.path)]
        for fd in files:
            if SNAPSHOT_PATH.search(fd.path):
                continue
            if TEST_PATH.search(fd.path):
                self.check_file(fd)
        if len(snapshot_files) > self.snapshot_threshold:
            self.add("SNAPSHOT_MASS_UPDATE", "block", "<snapshots>", None,
                     f"{len(snapshot_files)} snapshot/golden files changed (> {self.snapshot_threshold}); "
                     "mass updates hide regressions and need review")
        return self.report()

    def report(self) -> dict:
        open_block = [f for f in self.findings if f["severity"] == "block" and f["status"] == "open"]
        return {
            "classification": "FACT",
            "source": "test_integrity_guard.py",
            "findings": self.findings,
            "summary": {
                "total": len(self.findings),
                "open_blocking": len(open_block),
                "ac_covered": sum(1 for f in self.findings if f["status"] == "ac-covered"),
                "accepted": sum(1 for f in self.findings if f["status"] == "accepted"),
                "warnings": sum(1 for f in self.findings if f["severity"] == "warn"),
            },
            "verdict": "FAIL" if open_block else "PASS",
        }


def apply_overrides(report: dict, overrides: list[dict]) -> dict:
    by_id = {o["finding_id"]: o for o in overrides if o.get("finding_id") and o.get("ledger_entry")}
    for f in report["findings"]:
        o = by_id.get(f["id"])
        if o and f["status"] == "open":
            f["status"] = "accepted"
            f["accepted_by"] = o["ledger_entry"]
    open_block = [f for f in report["findings"] if f["severity"] == "block" and f["status"] == "open"]
    report["summary"]["open_blocking"] = len(open_block)
    report["summary"]["accepted"] = sum(1 for f in report["findings"] if f["status"] == "accepted")
    report["verdict"] = "FAIL" if open_block else "PASS"
    return report


def load_overrides_from_ledger(db_path: str) -> list[dict]:
    """Query the evidence ledger for REVIEWED DECISION entries that accept test-integrity findings.

    Expected entry shape: classification=DECISION, lifecycle_state=REVIEWED,
    metadata.test_integrity_override=true, metadata.finding_id=<id>.
    Only qa-diagnose (AGENT) or HUMAN actors may write these.
    """
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT entry_id, metadata FROM entries "
            "WHERE classification = 'DECISION' AND lifecycle_state = 'REVIEWED' "
            "AND actor_type IN ('AGENT', 'HUMAN') "
            "ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    overrides = []
    for row in rows:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        if meta.get("test_integrity_override") and meta.get("finding_id"):
            overrides.append({"finding_id": meta["finding_id"], "ledger_entry": row["entry_id"]})
    return overrides


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff")
    ap.add_argument("--head-root")
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--ac-changed", default="")
    ap.add_argument("--ac-changed-file")
    ap.add_argument("--snapshot-threshold", type=int, default=5)
    ap.add_argument("--overrides", help="(deprecated: use --ledger-db) local JSON [{finding_id, ledger_entry}]")
    ap.add_argument("--ledger-db", help="evidence_ledger.db path; overrides are read from the ledger instead of a local file")
    args = ap.parse_args(argv)
    try:
        if args.diff:
            text = Path(args.diff).read_text(encoding="utf-8", errors="replace")
            head_root = Path(args.head_root) if args.head_root else None
        elif args.base and args.head:
            text = diff_dirs(Path(args.base), Path(args.head))
            head_root = Path(args.head)
        else:
            raise ValueError("give --diff FILE or --base DIR --head DIR")
        ac = {a.strip() for a in args.ac_changed.split(",") if a.strip()}
        if args.ac_changed_file:
            ac |= set(json.loads(Path(args.ac_changed_file).read_text(encoding="utf-8")))
        bad = [a for a in ac if not AC_TAG.fullmatch(a)]
        if bad:
            raise ValueError(f"malformed AC ids: {bad}")
        report = Guard(ac, head_root, args.snapshot_threshold).run(parse_unified_diff(text))
        if args.ledger_db:
            report = apply_overrides(report, load_overrides_from_ledger(args.ledger_db))
        elif args.overrides:
            report = apply_overrides(report, json.loads(Path(args.overrides).read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
