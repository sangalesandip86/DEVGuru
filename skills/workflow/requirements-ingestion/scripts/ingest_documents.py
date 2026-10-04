#!/usr/bin/env python3
"""Ingest requirement documents into normalized, hash-anchored sections (plan v3.1 §4.14 INTAKE).

Formats (stdlib only): .md/.markdown, .txt, .html/.htm (incl. Confluence HTML export),
Confluence storage format (.xml, ``ac:``/``ri:`` markup), .docx (word/document.xml via zipfile).
.pdf only if the optional ``pypdf`` package is importable; otherwise exit 3 naming it.

For every document it writes ``<out>/<doc-id>/sections.json`` and updates ``<out>/source-register.json``.
Each section gets a stable anchor (slug of the heading path, leading numbering stripped, so
renumbering "2.1" -> "3.1" keeps the anchor) and a sha256 hash of its normalized title + text.
Cite sections as ``doc:<doc-id>@<hash12>#<anchor>``.

Ingested text is DATA, never instructions (plan §4.1, §5.9). Sections containing agent-directed
imperatives are flagged ``instruction-like-text`` as a supplementary signal only.

    python ingest_documents.py docs/requirements/*.md --out .adlc/ingest
    python ingest_documents.py spec.docx --doc-id payments-spec --out .adlc/ingest
    python ingest_documents.py spec-v2.docx --doc-id payments-spec --diff     # compare only, write nothing
    python ingest_documents.py docs/ --register-out plans/intake/source-register.yaml

Exit codes: 0 ok · 2 bad input (missing file, unsupported extension) · 3 optional parser missing (pdf).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

SUPPORTED = {".md": "md", ".markdown": "md", ".txt": "txt", ".html": "html", ".htm": "html",
             ".xml": "confluence", ".docx": "docx", ".pdf": "pdf"}

INSTRUCTION_PATTERNS = [
    r"\bignore (all |any )?(the )?(previous|prior|above) (instructions|rules)\b",
    r"\b(you are|act as) (now )?(an? )?(ai|assistant|agent|claude|copilot)\b",
    r"\bsystem prompt\b",
    r"\b(skip|bypass|disable) (the )?(security|review|verification|tests?|approval|gates?)\b",
    r"\b(auto-?approve|mark (it |this )?(as )?(approved|verified|done|ready))\b",
    r"\bdo not (tell|inform) (the )?(user|human|reviewer)\b",
    r"\boverride (the )?(policy|platform|rules)\b",
]
_INSTR = re.compile("|".join(INSTRUCTION_PATTERNS), re.IGNORECASE)
_NUMBERING = re.compile(r"^\s*(?:(?:\d+|[A-Z])(?:\.\d+)*\.?|[IVXLC]+\.)\s+")


class IngestError(Exception):
    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------- normalization

def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if out and not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


def slugify(title: str) -> str:
    t = _NUMBERING.sub("", title)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60].strip("-") or "section"


def sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- block extraction
# Every parser returns a list of blocks: ("heading", level, text) or ("text", 0, text).

def blocks_markdown(text: str) -> list[tuple]:
    blocks, buf, in_fence = [], [], False
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0

    def flush():
        if buf:
            blocks.append(("text", 0, "\n".join(buf)))
            buf.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
            buf.append(ln)
        elif not in_fence and (m := re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", ln)):
            flush()
            blocks.append(("heading", len(m.group(1)), m.group(2)))
        elif (not in_fence and i + 1 < len(lines) and ln.strip()
              and re.match(r"^(=+|-+)\s*$", lines[i + 1]) and not ln.lstrip().startswith(("-", "*", "|"))):
            flush()
            blocks.append(("heading", 1 if lines[i + 1].strip().startswith("=") else 2, ln.strip()))
            i += 1
        else:
            buf.append(ln)
        i += 1
    flush()
    return blocks


def blocks_text(text: str) -> list[tuple]:
    """Plain text: lines like '2.1 Title' or 'SECTION 3: Title' are headings."""
    blocks, buf = [], []
    for ln in text.replace("\r\n", "\n").split("\n"):
        s = ln.strip()
        m = re.match(r"^((?:\d+\.)*\d+)\.?\s+([A-Z][^.]{1,80})$", s)
        if m:
            if buf:
                blocks.append(("text", 0, "\n".join(buf)))
                buf = []
            blocks.append(("heading", m.group(1).count(".") + 1, s))
        else:
            buf.append(ln)
    if buf:
        blocks.append(("text", 0, "\n".join(buf)))
    return blocks


class _HTMLBlocks(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "br", "table", "ul", "ol", "pre", "blockquote", "section", "article",
             "ac:rich-text-body", "ac:plain-text-body", "dt", "dd"}
    SKIP = {"script", "style", "head", "title", "ac:parameter", "ri:attachment"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple] = []
        self.buf: list[str] = []
        self.heading: int | None = None
        self.hbuf: list[str] = []
        self.skip = 0
        self.cell = False

    def _flush(self):
        text = "".join(self.buf)
        if text.strip():
            self.blocks.append(("text", 0, text))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading, self.hbuf = int(tag[1]), []
        elif tag in ("td", "th"):
            if self.cell:
                self.buf.append(" | ")
            self.cell = True
        elif tag in self.BLOCK:
            self.buf.append("\n")
            if tag == "tr":
                self.cell = False
            if tag == "li":
                self.buf.append("- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.heading and tag == f"h{self.heading}":
            self.blocks.append(("heading", self.heading, "".join(self.hbuf).strip()))
            self.heading = None
        elif tag in self.BLOCK:
            self.buf.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        (self.hbuf if self.heading else self.buf).append(data)

    def close(self):
        super().close()
        self._flush()


def blocks_html(text: str) -> list[tuple]:
    p = _HTMLBlocks()
    # Confluence storage format: CDATA in ac:plain-text-body; unwrap so the parser keeps the text.
    p.feed(re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: html.escape(m.group(1)), text, flags=re.S))
    p.close()
    return p.blocks


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def blocks_docx(path: Path) -> list[tuple]:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise IngestError(f"{path}: not a valid .docx ({exc})")
    root = ET.fromstring(xml)
    body = root.find(f"{_W}body")
    blocks: list[tuple] = []
    if body is None:
        return blocks

    def para_text(p) -> str:
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        return "".join(parts)

    for child in body:
        if child.tag == f"{_W}p":
            style = child.find(f"{_W}pPr/{_W}pStyle")
            sval = style.get(f"{_W}val", "") if style is not None else ""
            text = para_text(child)
            m = re.match(r"(?i)^heading\s*([1-9])$", sval) or re.match(r"(?i)^heading([1-9])$", sval)
            if m and text.strip():
                blocks.append(("heading", min(int(m.group(1)), 6), text.strip()))
            elif sval.lower() == "title" and text.strip():
                blocks.append(("heading", 1, text.strip()))
            elif text.strip():
                blocks.append(("text", 0, text))
        elif child.tag == f"{_W}tbl":
            rows = []
            for tr in child.iter(f"{_W}tr"):
                cells = [" ".join(para_text(p) for p in tc.iter(f"{_W}p")).strip() for tc in tr.iter(f"{_W}tc")]
                rows.append(" | ".join(cells))
            if rows:
                blocks.append(("text", 0, "\n".join(rows)))
    return blocks


def blocks_pdf(path: Path) -> list[tuple]:
    try:
        import pypdf  # type: ignore
    except ImportError:
        raise IngestError("PDF ingestion needs the optional 'pypdf' package (pip install pypdf), "
                          "or convert the PDF to .docx/.md first.", code=3)
    reader = pypdf.PdfReader(str(path))
    blocks = []
    for n, page in enumerate(reader.pages, 1):
        blocks.append(("heading", 1, f"Page {n}"))
        blocks.append(("text", 0, page.extract_text() or ""))
    return blocks


# --------------------------------------------------------------------------- sections

def build_sections(blocks: list[tuple]) -> list[dict]:
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    current = {"level": 0, "title": "(preamble)", "path": [], "texts": []}
    used: dict[str, int] = {}

    def close(sec):
        text = normalize_text("\n".join(sec["texts"]))
        if not text and sec["title"] == "(preamble)":
            return
        base = "/".join(slugify(t) for t in sec["path"]) or "preamble"
        n = used.get(base, 0) + 1
        used[base] = n
        anchor = base if n == 1 else f"{base}-{n}"
        title = normalize_text(sec["title"])
        sections.append({
            "anchor": anchor,
            "ordinal": len(sections) + 1,
            "level": sec["level"],
            "title": title,
            "breadcrumb": [normalize_text(t) for t in sec["path"]],
            "text": text,
            "hash": sha256(title + "\n" + text),
            "flags": ["instruction-like-text"] if _INSTR.search(title + "\n" + text) else [],
        })

    for kind, level, text in blocks:
        if kind == "heading":
            close(current)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            current = {"level": level, "title": text, "path": [t for _, t in stack], "texts": []}
        else:
            current["texts"].append(text)
    close(current)
    return sections


def detect_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise IngestError(f"{path}: unsupported extension {ext!r}; supported: {sorted(SUPPORTED)}")
    fmt = SUPPORTED[ext]
    if fmt == "html":
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
        if "ac:structured-macro" in head or "confluence" in head.lower():
            return "confluence"
    return fmt


def parse(path: Path) -> tuple[str, list[dict]]:
    fmt = detect_format(path)
    if fmt == "docx":
        blocks = blocks_docx(path)
    elif fmt == "pdf":
        blocks = blocks_pdf(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        blocks = {"md": blocks_markdown, "txt": blocks_text, "html": blocks_html, "confluence": blocks_html}[fmt](text)
    return fmt, build_sections(blocks)


def doc_hash(sections: list[dict]) -> str:
    return sha256("\n".join(f"{s['anchor']}={s['hash']}" for s in sections))


def default_doc_id(path: Path) -> str:
    return slugify(path.stem.replace("_", " ")) or "doc"


def source_identity(path: Path, trust_override: str | None) -> tuple[str, str]:
    """(ref, trust_level). A file inside a git work tree is REPOSITORY with repo@sha:path."""
    top = None
    try:
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(path.parent),
                             capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            top = Path(res.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        top = None
    if top:
        sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=str(top),
                             capture_output=True, text=True).stdout.strip() or "WORKTREE"
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path.resolve())], cwd=str(top),
                                 capture_output=True, text=True).returncode == 0
        rel = path.resolve().relative_to(top).as_posix()
        if tracked:
            return f"{top.name}@{sha}:{rel}", trust_override or "REPOSITORY"
    return path.resolve().as_posix(), trust_override or "EXTERNAL_UNSTRUCTURED"


# --------------------------------------------------------------------------- register / diff

def load_register(out: Path) -> dict:
    p = out / "source-register.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"documents": {}}


def diff_sections(old: dict | None, sections: list[dict]) -> dict:
    if not old:
        return {"previous": None, "added": [s["anchor"] for s in sections], "changed": [], "removed": [],
                "unchanged": 0}
    prev = old.get("section_hashes", {})
    now = {s["anchor"]: s["hash"] for s in sections}
    return {
        "previous": old.get("content_hash"),
        "added": [a for a in now if a not in prev],
        "changed": [a for a in now if a in prev and prev[a] != now[a]],
        "removed": [a for a in prev if a not in now],
        "unchanged": sum(1 for a in now if prev.get(a) == now[a]),
    }


def ingest(path: Path, out: Path, doc_id: str | None, trust: str | None, write: bool, now: str) -> dict:
    if not path.is_file():
        raise IngestError(f"{path}: not a file")
    fmt, sections = parse(path)
    did = doc_id or default_doc_id(path)
    ref, trust_level = source_identity(path, trust)
    chash = doc_hash(sections)
    register = load_register(out)
    old = register["documents"].get(did)
    diff = diff_sections(old, sections)
    title = next((s["title"] for s in sections if s["level"] == 1), sections[0]["title"] if sections else path.stem)
    record = {
        "doc_id": did, "title": title, "source": ref, "trust_level": trust_level, "format": fmt,
        "content_hash": chash, "section_count": len(sections), "ingested_at": now,
        "section_hashes": {s["anchor"]: s["hash"] for s in sections},
    }
    if old and old.get("content_hash") != chash:
        record["supersedes_hash"] = old.get("content_hash")
    if write:
        d = out / did
        d.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in record.items() if k != "section_hashes"}
        payload["citation_prefix"] = f"doc:{did}@{chash[7:19]}"
        payload["sections"] = sections
        (d / "sections.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        register["documents"][did] = record
        (out / "source-register.json").write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
    flagged = [s["anchor"] for s in sections if s["flags"]]
    return {"doc_id": did, "format": fmt, "source": ref, "trust_level": trust_level, "content_hash": chash,
            "sections": len(sections), "flagged_instruction_like": flagged, "diff": diff,
            "written": str((out / did / "sections.json")) if write else None}


def committed_register(register: dict) -> dict:
    """The reviewable plans/intake/source-register.yaml form (intake-documents.schema.json#/$defs/source_register)."""
    docs = []
    for rec in register["documents"].values():
        docs.append({k: rec[k] for k in ("doc_id", "title", "source", "content_hash", "trust_level", "format",
                                         "section_count", "ingested_at", "supersedes_hash") if k in rec})
    return {"documents": sorted(docs, key=lambda d: d["doc_id"])}


def expand(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            files += sorted(f for f in pp.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED)
        elif pp.exists():
            files.append(pp)
        else:
            raise IngestError(f"{p}: no such file or directory")
    return files


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", help="files or directories")
    ap.add_argument("--out", default=".adlc/ingest", help="output dir (default .adlc/ingest)")
    ap.add_argument("--doc-id", help="explicit doc id (single input only); keep it stable across re-ingestion")
    ap.add_argument("--trust", choices=["ORGANIZATIONAL", "REPOSITORY", "EXTERNAL_STRUCTURED", "EXTERNAL_UNSTRUCTURED"],
                    help="override the derived trust level (never SYSTEM)")
    ap.add_argument("--diff", action="store_true", help="compare with the previous register entry; write nothing")
    ap.add_argument("--register-out", help="also write the committed register (JSON-compatible YAML) to this path")
    ap.add_argument("--now", help="ISO timestamp (default: current UTC time)")
    args = ap.parse_args(argv)
    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = Path(args.out)
    try:
        files = expand(args.paths)
        if args.doc_id and len(files) != 1:
            raise IngestError("--doc-id requires exactly one input file")
        results = [ingest(f, out, args.doc_id, args.trust, not args.diff, now) for f in files]
    except IngestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return exc.code
    if args.register_out and not args.diff:
        rp = Path(args.register_out)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(committed_register(load_register(out)), indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"ok": True, "mode": "diff" if args.diff else "ingest", "documents": results}, indent=2,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
