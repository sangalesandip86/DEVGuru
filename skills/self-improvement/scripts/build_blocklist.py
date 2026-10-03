#!/usr/bin/env python3
"""Build the per-project sanitization blocklist (ADR 0006 §4).

Collects terms that identify a project, so sanitize_check.py can stop them leaving project
scope:
  * glossary terms (plans/glossary*.{yaml,yml,json,md});
  * plan IDs and names/titles from plans/**/*.y*ml, plus distinctive identifiers found in
    plan text (CamelCase, mixed-case acronyms like "VaR", ALLCAPS, snake_case, hostnames);
  * repo names (directory, git remote, adlc.workspace.yaml repos[].name), system and
    service names from adlc.workspace.yaml;
  * CODEOWNERS handles and teams (and e-mail local parts / domains);
  * package names (package.json, pyproject.toml, setup.cfg, go.mod, Cargo.toml, pom.xml,
    pubspec.yaml, composer.json, *.csproj).
Common words are excluded: a built-in list plus every word that appears in the platform's own
skill catalog (generic by definition), and phrases that appear verbatim there.

Usage:  python build_blocklist.py --root PROJECT [--root PROJECT2 ...] [--out blocklist.json]
                                  [--generic-corpus skills/] [--no-generic-corpus]
Output: {"version", "generated_at", "terms", "by_source", "excluded_generic"}
Exit:   0 ok, 2 usage/setup error (e.g. a root does not exist)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".dart_tool", ".adlc"}
RESERVED_DOMAINS = ("example.com", "example.org", "example.net", "localhost")

COMMON = set("""
a an the and or not but if then else when while for with without from into onto over under of to in on at by as is are
was were be been being it its this that these those there here we you they he she them our your their my me us all any
each every some none no yes more most less least many much few other same such only own new old first last next
api app apps application service services server client clients web ui ux core common shared util utils utility lib libs
library main src source test tests testing spec specs mock mocks data db database model models view views controller
module modules package packages config configuration settings env dev prod staging local default admin user users
account accounts auth login logout session token id ids key keys value values name names type types item items list
error errors event events message messages queue job jobs task tasks worker workers backend frontend mobile android ios
platform system systems project projects team teams org owner owners docs doc readme changelog license build release
deploy deployment infra infrastructure ci cd pipeline pipelines workflow workflows github gitlab bitbucket git repo repos
http https json yaml yml xml csv html css js ts python java kotlin go rust ruby php dotnet node npm pip maven gradle
story stories epic epics feature features requirement requirements milestone milestones plan plans glossary title
description status draft ready done accepted blocked high low medium critical true false null none req feat
""".split())

CAMEL = re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*\b|\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b")
ACRONYM = re.compile(r"\b[A-Z]{3,}[0-9]*\b")
SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
HOST = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.I)
PLAN_ID = re.compile(r"\b(?:REQ|EPIC|FEAT|ST|MS)-\d+\b")
NAMED_KEYS = ("title", "name", "system", "service", "requested_by", "persona", "component", "team", "term", "acronym")


def iter_files(root: Path, patterns: tuple[str, ...], max_depth: int = 4):
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or len(rel.parts) > max_depth:
            continue
        if p.is_file() and any(p.match(pat) for pat in patterns):
            yield p


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def yaml_values(text: str, keys: tuple[str, ...]) -> list[str]:
    out = []
    for m in re.finditer(r"^\s*-?\s*(" + "|".join(keys) + r")\s*:\s*(.+?)\s*$", text, re.M):
        val = m.group(2).split(" #")[0].strip().strip("'\"")
        if val and val not in ("|", ">", "null", "~"):
            out.append(val)
    return out


def distinctive(text: str) -> set[str]:
    text = re.sub(r"^\s*-?\s*[\w-]+\s*:", "", text, flags=re.M)  # YAML keys are schema, not project terms
    found = set(CAMEL.findall(text)) | set(ACRONYM.findall(text)) | set(SNAKE.findall(text)) | set(PLAN_ID.findall(text))
    for host in HOST.findall(text):
        if not host.lower().endswith(RESERVED_DOMAINS) and not re.search(r"\.(md|py|ya?ml|json|ts|js|java|txt)$", host, re.I):
            found.add(host)
    return found


def from_plans(plans: Path) -> dict[str, set[str]]:
    res: dict[str, set[str]] = {"glossary": set(), "plans": set()}
    if not plans.is_dir():
        return res
    for g in iter_files(plans, ("glossary*.yaml", "glossary*.yml", "glossary*.json", "glossary*.md", "glossary/*")):
        text = read(g)
        if g.suffix == ".md":
            res["glossary"] |= set(re.findall(r"\*\*([^*]{2,60})\*\*", text))
            res["glossary"] |= {m.strip() for m in re.findall(r"^\|\s*([^|]{2,60}?)\s*\|", text, re.M)
                                if not set(m.strip()) <= set("-: ") and m.strip().lower() not in ("term", "name")}
        elif g.suffix == ".json":
            try:
                data = json.loads(text)
                items = data if isinstance(data, list) else data.get("terms", data)
                if isinstance(items, dict):
                    res["glossary"] |= set(items.keys())
                else:
                    res["glossary"] |= {i.get("term") or i.get("name") for i in items if isinstance(i, dict)} - {None}
            except (json.JSONDecodeError, AttributeError):
                pass
        else:
            res["glossary"] |= set(yaml_values(text, ("term", "name", "acronym")))
            res["glossary"] |= set(re.findall(r"^([A-Za-z][\w .-]{1,40}):\s*\S", text, re.M)) - {"version", "terms"}
        res["glossary"] |= distinctive(text)
    for f in iter_files(plans, ("*.yaml", "*.yml"), max_depth=6):
        text = read(f)
        res["plans"] |= set(yaml_values(text, ("id",)))
        res["plans"] |= {v for v in yaml_values(text, NAMED_KEYS) if len(v) <= 80}
        res["plans"] |= distinctive(text)
    return res


def from_repo(root: Path) -> dict[str, set[str]]:
    res = {k: set() for k in ("repos", "workspace", "codeowners", "packages")}
    res["repos"].add(root.resolve().name)
    gitcfg = root / ".git" / "config"
    for url in re.findall(r"^\s*url\s*=\s*(\S+)", read(gitcfg), re.M):
        segs = [s for s in re.split(r"[/:]", url.rstrip("/")) if s]
        if segs:
            res["repos"].add(re.sub(r"\.git$", "", segs[-1]))
        if len(segs) >= 2 and "." not in segs[-2] and "@" not in segs[-2]:
            res["repos"].add(segs[-2])
    ws = root / "adlc.workspace.yaml"
    if ws.is_file():
        text = read(ws)
        res["workspace"] |= set(yaml_values(text, ("name", "system", "service")))
    for co in (root / "CODEOWNERS", root / ".github" / "CODEOWNERS", root / "docs" / "CODEOWNERS"):
        for tok in re.findall(r"(?<!\S)@([\w.-]+(?:/[\w.-]+)?)", read(co)):
            res["codeowners"].add(tok)
            res["codeowners"] |= set(tok.split("/"))
        for local, domain in re.findall(r"([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)", read(co)):
            res["codeowners"].add(local)
            if not domain.lower().endswith(RESERVED_DOMAINS):
                res["codeowners"].add(domain)
    pk = res["packages"]
    for f in iter_files(root, ("package.json", "composer.json"), max_depth=3):
        try:
            name = json.loads(read(f)).get("name")
        except (json.JSONDecodeError, AttributeError):
            name = None
        if isinstance(name, str):
            pk.add(name)
            pk |= {p for p in name.lstrip("@").split("/") if p}
    for f in iter_files(root, ("pyproject.toml", "Cargo.toml", "setup.cfg"), max_depth=3):
        pk |= set(re.findall(r'^\s*name\s*=\s*["\']?([\w.@/-]+)', read(f), re.M))
    for f in iter_files(root, ("go.mod",), max_depth=3):
        for mod in re.findall(r"^module\s+(\S+)", read(f), re.M):
            pk.add(mod)
            pk |= set(mod.split("/")[1:])
    for f in iter_files(root, ("pom.xml",), max_depth=3):
        text = read(f)
        pk |= set(re.findall(r"<artifactId>([^<]+)</artifactId>", text)[:2])
        pk |= set(re.findall(r"<groupId>([^<]+)</groupId>", text)[:1])
    for f in iter_files(root, ("pubspec.yaml",), max_depth=3):
        pk |= set(yaml_values(read(f), ("name",))[:1])
    for f in iter_files(root, ("*.csproj",), max_depth=4):
        pk.add(f.stem)
    return res


def generic_vocab(corpus: Path | None) -> tuple[set[str], str]:
    words, text = set(COMMON), ""
    if corpus and corpus.is_dir():
        chunks = [read(p) for p in iter_files(corpus, ("*.md",), max_depth=6)]
        text = "\n".join(chunks).lower()
        words |= set(re.findall(r"[a-z][a-z0-9]+", text))
    return words, text


def is_generic(term: str, words: set[str], corpus_text: str) -> bool:
    t = term.strip()
    if len(t) < 3 or re.fullmatch(r"[\d\W_]+", t):
        return True
    low = t.lower()
    if " " in t or "-" in t or "/" in t:
        parts = re.findall(r"[a-z0-9]+", low)
        if PLAN_ID.fullmatch(t):
            return False
        return all(p in words for p in parts) and (len(parts) <= 1 or low in corpus_text)
    return low in words


def build(roots: list[Path], corpus: Path | None) -> dict:
    by_source: dict[str, set[str]] = {}
    for root in roots:
        for k, v in from_repo(root).items():
            by_source.setdefault(k, set()).update(v)
        plans_dirs = {root / "plans"}
        ws = root / "adlc.workspace.yaml"
        for pd in yaml_values(read(ws), ("plans_dir",)) if ws.is_file() else []:
            plans_dirs.add(root / pd)
        for pd in plans_dirs:
            for k, v in from_plans(pd).items():
                by_source.setdefault(k, set()).update(v)
    words, corpus_text = generic_vocab(corpus)
    excluded = 0
    clean: dict[str, list[str]] = {}
    for k, terms in by_source.items():
        keep = sorted({t.strip() for t in terms if t and t.strip()} , key=str.lower)
        kept = [t for t in keep if not is_generic(t, words, corpus_text)]
        excluded += len(keep) - len(kept)
        clean[k] = kept
    all_terms = sorted({t for v in clean.values() for t in v}, key=str.lower)
    return {"version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "roots": [r.resolve().name for r in roots], "terms": all_terms, "by_source": clean,
            "excluded_generic": excluded}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, action="append", required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--generic-corpus", type=Path, default=REPO / "skills")
    ap.add_argument("--no-generic-corpus", action="store_true")
    args = ap.parse_args(argv)
    missing = [r for r in args.root if not r.is_dir()]
    if missing:
        print(json.dumps({"error": f"root not found: {[m.as_posix() for m in missing]}"}))
        return 2
    result = build(args.root, None if args.no_generic_corpus else args.generic_corpus)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"out": args.out.as_posix(), "terms": len(result["terms"])}))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
