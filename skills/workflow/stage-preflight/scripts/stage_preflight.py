#!/usr/bin/env python3
"""Stage preflight: can a run start at stage X? (plan v3.1 §4.14, §4.15)

For every input the start stage requires (skills/workflow/stages.yaml), and for every repo role it
needs, classify:

  SATISFIED  the artifact exists and its gate passed (or it is optional and present)
  ADOPT      it exists outside the platform (tracker export, docs, existing code/tests) and was
             supplied with --adopt KIND=REF: import as DRAFT (brownfield-adoption), then the gate runs
  BACKFILL   missing: run the smallest upstream stage that produces it (or the conventions scan,
             or an inline story for LOW BUG_FIX/DOCUMENTATION)
  ASK        ambiguous or needs a human choice: one batched QUESTION with ranked options
  BLOCK      it exists but a gate failed on existing evidence: the exact missing items are listed

Starting late never switches a gate off; this script only decides what must happen first.
Unknown risk tier → HIGH (fail-safe, §5.3).

    python stage_preflight.py --start IMPLEMENT --story ST-12 --cwd ../payments-svc \\
        --plans ../acme-plans/plans --evidence evidence.json
    python stage_preflight.py --start INTAKE --end PLAN --adopt source-doc=docs/requirements/
    python stage_preflight.py --start TEST --mode characterization --workspace ws.json

Exit codes: 0 everything SATISFIED (proceed) · 1 action needed (ADOPT/BACKFILL/ASK/BLOCK) · 2 bad input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "lib"))
sys.path.insert(0, str(HERE.parents[2] / "workspace-resolver" / "scripts"))
import workflow_lib as wl  # noqa: E402

try:
    import readiness_gate  # planning-gates dir is on sys.path via workflow_lib
    import planning_lib as pl
    from ac_hash import ac_hash
except ImportError:  # pragma: no cover - planning gates are part of the platform
    readiness_gate = pl = ac_hash = None

ORDER = {"SATISFIED": 0, "ADOPT": 1, "BACKFILL": 2, "ASK": 3, "BLOCK": 4}
CODE_HINTS = ["src", "app", "lib", "pkg", "cmd", "internal", "services", "web"]
MANIFEST_HINTS = ["package.json", "pyproject.toml", "setup.py", "pom.xml", "build.gradle", "build.gradle.kts",
                  "go.mod", "Cargo.toml", "pubspec.yaml", "Gemfile", "composer.json"]


class PreflightError(Exception):
    pass


def outcome(kind: str, status: str, detail: str, remedy: str | None = None, **extra) -> dict:
    d = {"kind": kind, "outcome": status, "detail": detail}
    if remedy:
        d["remedy"] = remedy
    d.update(extra)
    return d


# --------------------------------------------------------------------------- context

class Ctx:
    def __init__(self, args, stages: dict, workspace: dict):
        self.args = args
        self.stages = stages
        self.workspace = workspace
        self.evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")) if args.evidence else {}
        roles = workspace.get("roles", {})
        planning = roles.get("planning", {})
        app = roles.get("app", {})
        self.planning_root = Path(planning["path"]) if planning.get("status") == "FOUND" else None
        self.app_root = Path(app["path"]) if app.get("status") == "FOUND" else None
        self.plans = Path(args.plans) if args.plans else (self.planning_root / "plans" if self.planning_root else None)
        self.architecture = (Path(args.architecture) if args.architecture
                             else (self.planning_root / "architecture" if self.planning_root else None))
        self.ingest = Path(args.ingest_dir) if args.ingest_dir else (
            (self.planning_root or Path(args.cwd)) / ".adlc" / "ingest")
        self.adopt = {}
        for item in args.adopt or []:
            k, _, ref = item.partition("=")
            if not ref:
                raise PreflightError(f"--adopt expects KIND=REF, got {item!r}")
            self.adopt.setdefault(k, []).append(ref)
        self.story = None
        self.story_id = args.story
        self._plans_cache = None
        self.tier = self._tier()

    # plans
    def plans_loaded(self):
        if self._plans_cache is None:
            if self.plans and self.plans.is_dir() and pl:
                self._plans_cache = pl.load_plans(self.plans)
            else:
                self._plans_cache = ({"requirement": {}, "epic": {}, "story": {}, "milestone": {}}, [])
        return self._plans_cache

    def _tier(self) -> dict:
        declared = self.args.tier
        story_type = self.args.story_type
        sources = {"declared": declared}
        tier = declared
        if self.args.story and pl:
            plans, _ = self.plans_loaded()
            story = plans["story"].get(self.args.story)
            if story:
                self.story = story
                story_type = story_type or story.get("type")
                try:
                    eff = pl.effective_tier(story, pl.load_policy("story-types"))
                    sources["story"] = eff
                    tier = pl.max_tier(tier, eff.get("tier"))
                except (OSError, ValueError, KeyError):
                    pass
        if tier not in wl.TIERS:
            sources["fail_safe"] = "tier unknown → HIGH (§5.3)"
            tier = "HIGH"
        return {"tier": tier, "story_type": story_type, "sources": sources}

    def required(self, cond: str) -> bool:
        if cond == "always":
            return True
        if cond == "never":
            return False
        if cond.startswith("tier>="):
            return wl.tier_at_least(self.tier["tier"], cond[len("tier>="):])
        if cond == "existing_repo":
            return self.existing_repo()
        raise PreflightError(f"unknown requirement condition {cond!r}")

    def existing_repo(self) -> bool:
        if self.args.existing_repo in ("yes", "no"):
            return self.args.existing_repo == "yes"
        if not self.app_root or not self.app_root.is_dir():
            return False
        return any((self.app_root / d).is_dir() for d in CODE_HINTS) or any(
            (self.app_root / m).exists() for m in MANIFEST_HINTS)

    def reviews(self, item: str, role: str) -> tuple[bool, str]:
        """Judgment: REVIEWED/ACCEPT from the role (AGENT) or a HUMAN; SYSTEM never counts (§5.5)."""
        verdict, notes = None, []
        for r in self.evidence.get("reviews", []):
            if r.get("item") != item:
                continue
            if r.get("actor_type") == "SYSTEM" or r.get("lifecycle_state", "REVIEWED") != "REVIEWED":
                notes.append("SYSTEM/VERIFIED evidence cannot satisfy a judgment")
                continue
            if r.get("actor_type") == "HUMAN" or (r.get("actor_type") == "AGENT" and r.get("role") == role):
                verdict = r.get("verdict")
        if verdict == "ACCEPT":
            return True, f"REVIEWED by {role}"
        if verdict == "REJECT":
            return False, f"{role} REJECTED — only a human lifts a domain rejection"
        return False, f"needs REVIEWED/ACCEPT from {role}" + (f" ({notes[0]})" if notes else "")

    def approved(self, item: str, approver: str) -> bool:
        return any(a.get("item") == item and a.get("approver") == approver and a.get("actor_type") == "HUMAN"
                   for a in self.evidence.get("approvals", []))


# --------------------------------------------------------------------------- per-kind checks

def _backfill(kind: str, spec: dict, ctx: Ctx, why: str) -> dict:
    if kind in ctx.adopt:
        return outcome(kind, "ADOPT", f"{why}; supplied externally: {ctx.adopt[kind]}",
                       "import as DRAFT via workflow/brownfield-adoption, then run the gate", refs=ctx.adopt[kind])
    bf = spec.get("backfill", {})
    target = bf.get("default", "ASK")
    if target == "ASK":
        return outcome(kind, "ASK", why, "supply the source material (documents, tracker export, or the request text)",
                       options=["point to requirement documents (--adopt source-doc=PATH)",
                                "provide a tracker export (--adopt source-doc=export.json)",
                                "state the request in the session (recorded as a user statement)"])
    if target == "RUN_CONVENTION_SCAN":
        return outcome(kind, "BACKFILL", why,
                       "run skills/engineering-design/project-conventions/scripts/convention_scan.py "
                       f"--repo {ctx.app_root or '<app repo>'} [--target <path you will change>]",
                       backfill_stage=None)
    return outcome(kind, "BACKFILL", why, f"run stage {target} first (smallest run that produces {kind})",
                   backfill_stage=target)


def check_source_doc(spec, ctx):
    reg_paths = [ctx.ingest / "source-register.json"]
    if ctx.plans:
        reg_paths.append(ctx.plans / "intake" / "source-register.yaml")
    for p in reg_paths:
        if p.is_file():
            data = wl.load_yaml(p)
            docs = data.get("documents", {})
            n = len(docs)
            if n:
                return outcome("source-doc", "SATISFIED", f"{n} registered document(s) in {p}")
    return _backfill("source-doc", spec, ctx, "no ingested/registered source documents")


def check_requirement(spec, ctx):
    plans, errors = ctx.plans_loaded()
    reqs = plans["requirement"]
    if not reqs:
        return _backfill("requirement", spec, ctx, "no plans/requirements/REQ-*.yaml")
    schema = pl.load_schema("requirement")
    problems = [e for e in errors if "/requirements/" in e["file"].replace("\\", "/")]
    for rid, doc in reqs.items():
        problems += [{"file": doc["_file"], "error": e} for e in pl.validate(doc, schema)]
    if problems:
        return outcome("requirement", "BLOCK", f"{len(problems)} requirement file problem(s)",
                       "fix the REQ files (plan_lint.py shows the same errors)", missing=problems[:10])
    return outcome("requirement", "SATISFIED", f"{len(reqs)} valid requirement(s)")


def check_intake_file(kind: str, fname: str, defname: str):
    def _check(spec, ctx):
        p = ctx.plans / "intake" / fname if ctx.plans else None
        if not p or not p.is_file():
            return _backfill(kind, spec, ctx, f"missing plans/intake/{fname}")
        data = wl.load_yaml(p)
        schema = wl.load_schema("intake-documents")
        errs = wl.validate(data, {**schema, **schema["$defs"][defname]})
        if kind == "nfr-catalog" and not errs:
            for n in data.get("nfrs", []):
                if not n.get("target") and not n.get("open_question"):
                    errs.append(f"{n.get('id')}: unquantified NFR without an open_question (raise a QUESTION)")
        if errs:
            return outcome(kind, "BLOCK", f"{fname} invalid", f"fix plans/intake/{fname}", missing=errs[:10])
        return outcome(kind, "SATISFIED", f"plans/intake/{fname} valid")
    return _check


def intake_coverage(ctx) -> dict | None:
    """INTAKE exit check: every ingested section appears in the traceability matrix."""
    reg = ctx.ingest / "source-register.json"
    tm = ctx.plans / "intake" / "traceability-matrix.yaml" if ctx.plans else None
    if not reg.is_file() or not tm or not tm.is_file():
        return None
    register = wl.load_json(reg)
    rows = wl.load_yaml(tm).get("rows", [])
    covered = {(r["source"], r.get("section_hash")) for r in rows}
    by_source = {r["source"] for r in rows}
    missing, stale = [], []
    for did, rec in register.get("documents", {}).items():
        for anchor, h in rec.get("section_hashes", {}).items():
            key = f"{did}#{anchor}"
            if key not in by_source:
                missing.append(key)
            elif (key, h) not in covered:
                stale.append(key)
    status = "SATISFIED" if not missing and not stale else "BLOCK"
    return outcome("traceability-matrix", status,
                   "every ingested section is dispositioned" if status == "SATISFIED"
                   else f"{len(missing)} section(s) not in the matrix, {len(stale)} with a changed hash",
                   None if status == "SATISFIED" else "add a row per section (COVERED/PARTIAL/NOT_REQUIREMENT/QUESTION/"
                                                      "OUT_OF_SCOPE); re-review rows whose section hash changed",
                   missing=missing[:20], stale=stale[:20])


def check_architecture(spec, ctx):
    a = ctx.architecture
    present = bool(a and (a / "README.md").is_file() and (a / "service-map.yaml").is_file())
    if not present:
        if spec.get("adopt_only"):
            if "architecture-package" in ctx.adopt:
                return outcome("architecture-package", "ADOPT", "current-state architecture supplied",
                               "import via brownfield-adoption as the ARCHITECTURE baseline (delta, not redesign)",
                               refs=ctx.adopt["architecture-package"])
            return outcome("architecture-package", "SATISFIED", "no current-state package (optional input)")
        return _backfill("architecture-package", spec, ctx, "no architecture/README.md + architecture/service-map.yaml")
    if spec.get("adopt_only"):
        return outcome("architecture-package", "SATISFIED",
                       "current-state architecture present: this run produces a DELTA against it (§4.15)")
    ok, why = ctx.reviews("architecture_review", "architect")
    missing = [] if ok else [why]
    superseding = any(e.get("superseding_adr") for e in ctx.evidence.get("adrs", []))
    if (wl.tier_at_least(ctx.tier["tier"], "HIGH") or superseding) and not ctx.approved("architecture_approval",
                                                                                         "human:tech-lead"):
        missing.append("needs authenticated APPROVAL from human:tech-lead"
                       + (" (an ADR supersedes an existing decision)" if superseding else ""))
    if missing:
        return outcome("architecture-package", "BLOCK", "architecture package present but not accepted",
                       "obtain the missing review/approval (degraded mode: architect → human:tech-lead)",
                       missing=missing)
    return outcome("architecture-package", "SATISFIED", "architecture package reviewed"
                   + (" and approved" if wl.tier_at_least(ctx.tier["tier"], "HIGH") else ""))


def _pick_story(ctx, kind, spec):
    plans, _ = ctx.plans_loaded()
    stories = plans["story"]
    if ctx.story_id:
        if ctx.story_id not in stories:
            return None, _backfill(kind, spec, ctx, f"story {ctx.story_id} not found under plans/stories")
        return stories[ctx.story_id], None
    if len(stories) == 1:
        sid = next(iter(stories))
        ctx.story_id = sid
        return stories[sid], None
    if not stories:
        return None, None
    return None, outcome(kind, "ASK", f"{len(stories)} stories exist; which one is this run for?",
                         "re-run with --story ST-n", options=sorted(stories)[:15])


def check_ready_story(spec, ctx):
    story, early = _pick_story(ctx, "ready-story", spec)
    if early:
        return early
    if story is None:
        inline = spec.get("backfill", {}).get("inline_story")
        st = ctx.tier["story_type"]
        if inline and st in inline["story_types"] and not wl.tier_at_least(ctx.tier["tier"], "MEDIUM"):
            return outcome("ready-story", "BACKFILL", f"no story; {st} at tier {ctx.tier['tier']}",
                           "write an inline story in the PR body (still checked by the readiness gate)",
                           backfill_stage=None, mode="INLINE_STORY")
        if "ready-story" in ctx.adopt or "story" in ctx.adopt:
            return outcome("ready-story", "ADOPT", "story supplied from an external tracker",
                           "import via brownfield-adoption into plans/inbox, promote with story-writer, then "
                           "readiness_gate", refs=ctx.adopt.get("ready-story") or ctx.adopt.get("story"))
        why = "no story under plans/stories"
        if wl.tier_at_least(ctx.tier["tier"], "HIGH"):
            why += f"; tier {ctx.tier['tier']} never writes code before a READY story"
        return _backfill("ready-story", spec, ctx, why)
    res = readiness_gate.evaluate(ctx.plans, story["id"], ctx.evidence)
    if res["result"] == "READY":
        return outcome("ready-story", "SATISFIED", f"{story['id']} READY (ac_hash {res['ac_hash'][:19]}…)",
                       story=story["id"], ac_hash=res["ac_hash"])
    missing = [f"{i['id']} [{i['check']}]: {i['detail']}" for i in res["items"] if i["status"] != "PASS"]
    return outcome("ready-story", "BLOCK", f"{story['id']} NOT_READY ({len(missing)} item(s))",
                   "BACKFILL PLAN (refinement only) for the missing items", missing=missing, story=story["id"],
                   backfill_stage="PLAN")


def check_test_design(spec, ctx):
    if ctx.args.mode == "characterization":
        return outcome("test-design", "SATISFIED",
                       "characterization mode: oracle = current behaviour, recorded as an ASSUMPTION",
                       "tag tests `characterization`; they never count as AC verification or VERIFIED on a story",
                       mode="CHARACTERIZATION")
    plans, _ = ctx.plans_loaded()
    story, early = _pick_story(ctx, "test-design", spec)
    if early and early["outcome"] == "ASK":
        return early
    if story is None:
        if spec.get("backfill", {}).get("characterization"):
            return outcome("test-design", "ASK", "no story / acceptance criteria to derive tests from",
                           "choose how to establish the oracle",
                           options=["characterization tests of current behaviour (--mode characterization)",
                                    "BACKFILL PLAN + DESIGN: write the story and AC first"])
        return _backfill("test-design", spec, ctx, "no story to design tests for")
    design = ctx.plans / "test-designs" / f"{story['id']}.yaml" if ctx.plans else None
    if design and design.is_file():
        doc = wl.load_yaml(design)
        current = ac_hash(story)
        if doc.get("ac_hash") != current:
            return outcome("test-design", "BLOCK", f"test design for {story['id']} is stale (AC changed after freeze)",
                           "qa-derive writes a NEW design for the current AC; never edit the old one",
                           backfill_stage="DESIGN", expected_ac_hash=current, found=doc.get("ac_hash"))
        return outcome("test-design", "SATISFIED", f"frozen test design for {story['id']} matches the AC hash")
    feature_tag = f"@{story['id']}"
    roots = [r for r in (ctx.app_root, ctx.planning_root) if r]
    for root in roots:
        for f in root.rglob("*.feature"):
            try:
                if feature_tag in f.read_text(encoding="utf-8", errors="replace"):
                    return outcome("test-design", "SATISFIED", f"Gherkin design tagged {feature_tag}: {f}")
            except OSError:
                continue
    return _backfill("test-design", spec, ctx, f"no plans/test-designs/{story['id']}.yaml or *.feature tagged "
                                               f"{feature_tag}")


def _declared_files(catalog: dict) -> list[dict]:
    ds = catalog.get("declared_standards", {})
    files = []
    for key in ("docs", "lint", "format", "type", "arch_conformance"):
        files += [f for f in ds.get(key, []) if isinstance(f, dict) and "path" in f]
    for d in ds.get("adr_dirs", []):
        files += d.get("files", [])
    return files


def check_conventions(spec, ctx):
    if not ctx.app_root:
        return outcome("conventions-catalog", "ASK", "app repo not resolved; cannot scan conventions",
                       "resolve the app repo first (see workspace section)")
    path = Path(ctx.args.conventions) if ctx.args.conventions else ctx.app_root / ".adlc" / "catalog" / "conventions.json"
    if not path.is_file():
        return _backfill("conventions-catalog", spec, ctx, f"existing repo has no conventions catalog ({path})")
    catalog = wl.load_json(path)
    stale = []
    head = wl.git(["rev-parse", "HEAD"], ctx.app_root)
    if catalog.get("head_sha") and head and catalog["head_sha"] != head:
        stale.append(f"catalog scanned at {catalog['head_sha'][:12]}, HEAD is {head[:12]}")
    for f in _declared_files(catalog):
        p = ctx.app_root / f["path"]
        if not p.is_file():
            stale.append(f"declared standard removed: {f['path']}")
        elif f.get("sha256") and _sha256(p) != f["sha256"].replace("sha256:", ""):
            stale.append(f"declared standard changed: {f['path']}")
    for m in MANIFEST_HINTS:
        p = ctx.app_root / m
        if p.is_file() and p.stat().st_mtime > path.stat().st_mtime:
            stale.append(f"dependency manifest newer than catalog: {m}")
    if stale:
        return outcome("conventions-catalog", "BACKFILL", "conventions catalog is stale for this snapshot",
                       "re-run convention_scan.py (cached per snapshot; manifests/standards changed)",
                       missing=stale[:10], backfill_stage=None)
    return outcome("conventions-catalog", "SATISFIED", f"fresh conventions catalog ({path.name})",
                   greenfield=catalog.get("greenfield"))


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _evidence_kind(kind: str, key: str, describe: str):
    def _check(spec, ctx):
        sid = ctx.story_id
        recs = [r for r in ctx.evidence.get(key, []) if not sid or r.get("story") in (sid, None)]
        if kind == "change-set":
            recs = [r for r in recs if r.get("state") in ("VERIFYING", "INTEGRATED", "RELEASED", None)]
        if kind == "review-verdict":
            recs = [r for r in recs if r.get("item") in ("code_review_accept", "security_review")
                    and r.get("verdict") == "ACCEPT" and r.get("actor_type") != "SYSTEM"]
        if recs:
            return outcome(kind, "SATISFIED", f"{len(recs)} {describe} record(s) in the evidence export")
        if kind in ctx.adopt:
            return outcome(kind, "ADOPT", f"{describe} supplied externally", "import via brownfield-adoption",
                           refs=ctx.adopt[kind])
        if not spec.get("required", "always") == "never":
            return _backfill(kind, spec, ctx, f"no {describe} in the evidence export")
        return outcome(kind, "SATISFIED", f"no {describe} (optional)")
    return _check


def check_test_suite(spec, ctx):
    root = ctx.app_root
    if root:
        for pat in ctx.stages["artifact_kinds"]["test-suite"]["locations"]:
            if next(root.glob(pat), None):
                return outcome("test-suite", "SATISFIED", f"tests present in {root.name} ({pat})")
    return _backfill("test-suite", spec, ctx, "no test suite found in the app repo")


CHECKS = {
    "source-doc": check_source_doc,
    "requirement": check_requirement,
    "nfr-catalog": check_intake_file("nfr-catalog", "nfr-catalog.yaml", "nfr_catalog"),
    "glossary": check_intake_file("glossary", "glossary.yaml", "glossary"),
    "architecture-package": check_architecture,
    "ready-story": check_ready_story,
    "test-design": check_test_design,
    "conventions-catalog": check_conventions,
    "change-set": _evidence_kind("change-set", "change_sets", "Change Set"),
    "review-verdict": _evidence_kind("review-verdict", "reviews", "review verdict"),
    "release-record": _evidence_kind("release-record", "deployments", "deployment"),
    "incident": _evidence_kind("incident", "incidents", "incident"),
    "test-suite": check_test_suite,
}


# --------------------------------------------------------------------------- driver

def workspace_section(stage: dict, workspace: dict) -> list[dict]:
    out = []
    roles = workspace.get("roles", {})
    for role in stage["repo_roles"]["required"]:
        e = roles.get(role, {"status": "MISSING"})
        if e["status"] == "FOUND":
            out.append(outcome(f"repo:{role}", "SATISFIED", f"{e.get('name') or e.get('path')} @ "
                                                            f"{(e.get('head_sha') or 'no-commit')[:12]}"))
        elif e["status"] == "AMBIGUOUS":
            out.append(outcome(f"repo:{role}", "ASK", "several candidate repositories",
                               "choose one (--repo ROLE=PATH)",
                               options=[c.get("path") for c in e.get("candidates", [])]))
        else:
            out.append(outcome(f"repo:{role}", "ASK", e.get("hint") or f"no repository with role {role}",
                               "point to it, create it locally, or request a remote repo",
                               options=e.get("options") or ["--repo ROLE=PATH", f"--init-local {role} PATH",
                                                            f"--request-remote {role}"]))
    return out


def preflight(args) -> dict:
    stages = wl.load_stages(Path(args.stages) if args.stages else None)
    order = stages["order"]
    if args.start not in order:
        raise PreflightError(f"unknown start stage {args.start!r}; expected one of {order}")
    end = args.end or args.start
    if end not in order:
        raise PreflightError(f"unknown end stage {end!r}")
    if order.index(end) < order.index(args.start):
        raise PreflightError(f"end stage {end} comes before start stage {args.start}")
    if args.mode == "characterization" and args.start != "TEST":
        raise PreflightError("characterization mode is only valid when starting at TEST")
    if args.workspace:
        workspace = wl.load_json(Path(args.workspace))
    else:
        import resolve_workspace as rw
        rr = stages["stages"][args.start]["repo_roles"]
        workspace = rw.resolve(rr["required"], Path(args.cwd), {}, rr["optional"])
    stage = stages["stages"][args.start]
    ctx = Ctx(args, stages, workspace)
    results = workspace_section(stage, workspace)
    for spec in stage["inputs"]:
        kind = spec["kind"]
        if not ctx.required(spec["required"]) and not spec.get("adopt_only") and spec["required"] != "never":
            results.append(outcome(kind, "SATISFIED", f"not required ({spec['required']} is false for tier "
                                                      f"{ctx.tier['tier']})"))
            continue
        fn = CHECKS.get(kind)
        if fn is None:
            raise PreflightError(f"no preflight check for artifact kind {kind!r}")
        if spec["required"] == "never" and not spec.get("adopt_only"):
            res = fn(spec, ctx)
            if res["outcome"] in ("BACKFILL", "ASK", "BLOCK"):
                res = outcome(kind, "SATISFIED", f"optional input absent ({res['detail']})")
            results.append(res)
            continue
        results.append(fn(spec, ctx))
    if args.start == "INTAKE" or args.check_intake_coverage:
        cov = intake_coverage(ctx)
        if cov:
            results.append(cov)
    worst = max((r["outcome"] for r in results), key=ORDER.get, default="SATISFIED")
    rng = order[order.index(args.start): order.index(end) + 1]
    observed = [s for s in rng if stages["stages"][s]["observed_only"]]
    lead = stage["lead_roles"]
    degraded = {r: stages["degraded_mode"][r] for r in lead if r in stages["degraded_mode"]}
    return {
        "start": args.start, "end": end, "stages_in_range": rng,
        "observed_only_in_range": observed,
        "effective_tier": ctx.tier, "story": ctx.story_id,
        "mode": args.mode,
        "inputs": results,
        "overall": "PROCEED" if worst == "SATISFIED" else worst,
        "exit_gate": stage["exit_gate"],
        "lead_roles": lead,
        "degraded_mode_if_role_unavailable": degraded,
        "summary": summarize(args.start, end, results, worst, observed),
    }


def summarize(start, end, results, worst, observed) -> str:
    lines = [f"Preflight {start}" + (f" → {end}" if end != start else "") + f": {worst if worst != 'SATISFIED' else 'PROCEED'}"]
    for r in results:
        lines.append(f"  [{r['outcome']:<9}] {r['kind']}: {r['detail']}" + (f" → {r['remedy']}" if r.get("remedy") else ""))
    if observed:
        lines.append(f"  note: {', '.join(observed)} are observed events — the run stops when they are reached")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True)
    ap.add_argument("--end")
    ap.add_argument("--story")
    ap.add_argument("--tier", choices=wl.TIERS)
    ap.add_argument("--story-type")
    ap.add_argument("--mode", choices=["normal", "characterization"], default="normal")
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--workspace", help="resolve_workspace.py JSON output (default: resolve now from --cwd)")
    ap.add_argument("--plans", help="plans/ dir (default: <planning repo>/plans)")
    ap.add_argument("--architecture", help="architecture/ dir (default: <planning repo>/architecture)")
    ap.add_argument("--ingest-dir", help="ingestion output dir (default: <planning repo>/.adlc/ingest)")
    ap.add_argument("--evidence", help="SYSTEM evidence export (reviews, approvals, questions, change_sets, …)")
    ap.add_argument("--conventions", help="conventions catalog path (default: <app>/.adlc/catalog/conventions.json)")
    ap.add_argument("--existing-repo", choices=["auto", "yes", "no"], default="auto")
    ap.add_argument("--adopt", action="append", metavar="KIND=REF", help="artifact available outside the platform")
    ap.add_argument("--check-intake-coverage", action="store_true")
    ap.add_argument("--stages", help="alternate stages.yaml (tests)")
    ap.add_argument("--format", choices=["json", "text"], default="json")
    args = ap.parse_args(argv)
    try:
        res = preflight(args)
    except (PreflightError, ValueError, LookupError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(res["summary"] if args.format == "text" else wl.dump(res))
    return 0 if res["overall"] == "PROCEED" else 1


if __name__ == "__main__":
    sys.exit(main())
