import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage_preflight as sp  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
EXAMPLES = REPO / "examples" / "plans"


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = sp.main(args)
    out = buf.getvalue()
    return code, json.loads(out)


def by_kind(res):
    return {r["kind"]: r for r in res["inputs"]}


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.planning = self.root / "acme-plans"
        self.planning.mkdir()
        shutil.copytree(EXAMPLES / "requirements", self.planning / "plans" / "requirements")
        shutil.copytree(EXAMPLES / "epics", self.planning / "plans" / "epics")
        shutil.copytree(EXAMPLES / "milestones", self.planning / "plans" / "milestones")
        shutil.copytree(EXAMPLES / "stories", self.planning / "plans" / "stories")
        self.evidence = EXAMPLES / "evidence" / "evidence.json"
        self.app = self.root / "svc"
        (self.app / "src").mkdir(parents=True)
        (self.app / "package.json").write_text("{}", encoding="utf-8")
        self.ws = self._workspace()

    def tearDown(self):
        self.tmp.cleanup()

    def _workspace(self, **roles):
        default = {
            "planning": {"status": "FOUND", "path": str(self.planning), "name": "acme-plans", "head_sha": None},
            "app": {"status": "FOUND", "path": str(self.app), "name": "svc", "head_sha": None},
        }
        default.update(roles)
        p = self.root / "ws.json"
        p.write_text(json.dumps({"roles": default}), encoding="utf-8")
        return str(p)

    def base(self, *extra):
        return ["--workspace", self.ws, *extra]

    def scan_conventions(self):
        cat = self.app / ".adlc" / "catalog"
        cat.mkdir(parents=True, exist_ok=True)
        (cat / "conventions.json").write_text(json.dumps({"schema": "adlc.conventions/v1", "greenfield": False,
                                                          "declared_standards": {}}), encoding="utf-8")

    # ---------------------------------------------------------------- IMPLEMENT
    def test_implement_with_ready_story_and_fresh_conventions_proceeds(self):
        self.scan_conventions()
        code, res = run(self.base("--start", "IMPLEMENT", "--story", "ST-1", "--evidence", str(self.evidence)))
        k = by_kind(res)
        self.assertEqual(k["ready-story"]["outcome"], "SATISFIED", k["ready-story"])
        self.assertEqual(k["conventions-catalog"]["outcome"], "SATISFIED")
        self.assertEqual(res["overall"], "PROCEED", res["summary"])
        self.assertEqual(code, 0)

    def test_existing_repo_without_conventions_backfills_scan(self):
        code, res = run(self.base("--start", "IMPLEMENT", "--story", "ST-1", "--evidence", str(self.evidence)))
        c = by_kind(res)["conventions-catalog"]
        self.assertEqual(c["outcome"], "BACKFILL")
        self.assertIn("convention_scan.py", c["remedy"])
        self.assertEqual(code, 1)

    def test_stale_conventions_after_standard_changes(self):
        (self.app / ".eslintrc.json").write_text("{}", encoding="utf-8")
        cat = self.app / ".adlc" / "catalog"
        cat.mkdir(parents=True)
        (cat / "conventions.json").write_text(json.dumps({"declared_standards": {"lint": [
            {"path": ".eslintrc.json", "sha256": "0" * 64}]}}), encoding="utf-8")
        res = run(self.base("--start", "DESIGN", "--story", "ST-1", "--evidence", str(self.evidence)))[1]
        c = by_kind(res)["conventions-catalog"]
        self.assertEqual(c["outcome"], "BACKFILL")
        self.assertIn("declared standard changed: .eslintrc.json", c["missing"])

    def test_greenfield_app_repo_does_not_need_conventions(self):
        shutil.rmtree(self.app)
        self.app.mkdir()
        res = run(self.base("--start", "IMPLEMENT", "--story", "ST-1", "--evidence", str(self.evidence)))[1]
        self.assertIn("not required", by_kind(res)["conventions-catalog"]["detail"])

    def test_not_ready_story_blocks_with_missing_items(self):
        self.scan_conventions()
        code, res = run(self.base("--start", "IMPLEMENT", "--story", "ST-4", "--evidence", str(self.evidence)))
        r = by_kind(res)["ready-story"]
        self.assertEqual(r["outcome"], "BLOCK")
        self.assertTrue(r["missing"])
        self.assertEqual(r["backfill_stage"], "PLAN")
        self.assertEqual(res["overall"], "BLOCK")

    def test_low_bug_fix_without_story_gets_inline_story(self):
        shutil.rmtree(self.planning / "plans" / "stories")
        self.scan_conventions()
        res = run(self.base("--start", "IMPLEMENT", "--tier", "LOW", "--story-type", "BUG_FIX"))[1]
        r = by_kind(res)["ready-story"]
        self.assertEqual(r["outcome"], "BACKFILL")
        self.assertEqual(r["mode"], "INLINE_STORY")

    def test_unknown_tier_without_story_backfills_plan_and_is_high(self):
        shutil.rmtree(self.planning / "plans" / "stories")
        self.scan_conventions()
        res = run(self.base("--start", "IMPLEMENT", "--story-type", "BUG_FIX"))[1]
        self.assertEqual(res["effective_tier"]["tier"], "HIGH")
        r = by_kind(res)["ready-story"]
        self.assertEqual(r["backfill_stage"], "PLAN")
        self.assertIn("never writes code before a READY story", r["detail"])
        self.assertIn("test-design", by_kind(res))  # tier>=HIGH requires a test design too

    def test_multiple_stories_without_story_flag_asks(self):
        self.scan_conventions()
        res = run(self.base("--start", "IMPLEMENT", "--tier", "LOW"))[1]
        self.assertEqual(by_kind(res)["ready-story"]["outcome"], "ASK")

    def test_adopted_tracker_story(self):
        shutil.rmtree(self.planning / "plans" / "stories")
        self.scan_conventions()
        res = run(self.base("--start", "IMPLEMENT", "--tier", "MEDIUM", "--adopt", "story=jira-export.json"))[1]
        self.assertEqual(by_kind(res)["ready-story"]["outcome"], "ADOPT")

    # ---------------------------------------------------------------- TEST
    def test_test_stage_without_any_story_asks_characterization_or_backfill(self):
        shutil.rmtree(self.planning / "plans" / "stories")
        res = run(self.base("--start", "TEST"))[1]
        r = by_kind(res)["test-design"]
        self.assertEqual(r["outcome"], "ASK")
        self.assertEqual(len(r["options"]), 2)

    def test_characterization_mode(self):
        shutil.rmtree(self.planning / "plans" / "stories")
        res = run(self.base("--start", "TEST", "--mode", "characterization"))[1]
        r = by_kind(res)["test-design"]
        self.assertEqual(r["outcome"], "SATISFIED")
        self.assertIn("never count as AC verification", r["remedy"])
        code, err = run(self.base("--start", "IMPLEMENT", "--mode", "characterization"))
        self.assertEqual(code, 2)

    def test_frozen_and_stale_test_design(self):
        from ac_hash import ac_hash
        import planning_lib as pl
        plans, _ = pl.load_plans(self.planning / "plans")
        h = ac_hash(plans["story"]["ST-1"])
        td = self.planning / "plans" / "test-designs"
        td.mkdir(parents=True)
        (td / "ST-1.yaml").write_text(json.dumps({"story": "ST-1", "ac_hash": h}), encoding="utf-8")
        res = run(self.base("--start", "TEST", "--story", "ST-1"))[1]
        self.assertEqual(by_kind(res)["test-design"]["outcome"], "SATISFIED")
        (td / "ST-1.yaml").write_text(json.dumps({"story": "ST-1", "ac_hash": "sha256:old"}), encoding="utf-8")
        res = run(self.base("--start", "TEST", "--story", "ST-1"))[1]
        r = by_kind(res)["test-design"]
        self.assertEqual(r["outcome"], "BLOCK")
        self.assertIn("NEW design", r["remedy"])

    # ---------------------------------------------------------------- INTAKE / ARCHITECTURE / PLAN
    def test_intake_without_sources_asks_with_options(self):
        res = run(self.base("--start", "INTAKE", "--end", "PLAN"))[1]
        r = by_kind(res)["source-doc"]
        self.assertEqual(r["outcome"], "ASK")
        self.assertEqual(res["stages_in_range"], ["INTAKE", "ARCHITECTURE", "PLAN"])
        res = run(self.base("--start", "INTAKE", "--adopt", "source-doc=docs/requirements/"))[1]
        self.assertEqual(by_kind(res)["source-doc"]["outcome"], "ADOPT")

    def test_intake_coverage_detects_undispositioned_sections(self):
        ingest = self.planning / ".adlc" / "ingest"
        ingest.mkdir(parents=True)
        h = "sha256:" + "a" * 64
        (ingest / "source-register.json").write_text(json.dumps({"documents": {"payments": {
            "section_hashes": {"intro": h, "refunds": "sha256:" + "b" * 64}}}}), encoding="utf-8")
        intake = self.planning / "plans" / "intake"
        intake.mkdir(parents=True)
        (intake / "traceability-matrix.yaml").write_text(json.dumps({"rows": [
            {"source": "payments#intro", "section_hash": h, "disposition": "COVERED", "reqs": ["REQ-1"]}]}),
            encoding="utf-8")
        res = run(self.base("--start", "INTAKE"))[1]
        r = by_kind(res)["traceability-matrix"]
        self.assertEqual(r["outcome"], "BLOCK")
        self.assertEqual(r["missing"], ["payments#refunds"])

    def test_architecture_needs_intake_outputs(self):
        res = run(self.base("--start", "ARCHITECTURE"))[1]
        k = by_kind(res)
        self.assertEqual(k["requirement"]["outcome"], "SATISFIED")
        self.assertEqual(k["nfr-catalog"]["outcome"], "BACKFILL")
        self.assertEqual(k["nfr-catalog"]["backfill_stage"], "INTAKE")

    def test_unquantified_nfr_blocks(self):
        intake = self.planning / "plans" / "intake"
        intake.mkdir(parents=True)
        (intake / "nfr-catalog.yaml").write_text(json.dumps({"nfrs": [
            {"id": "NFR-1", "category": "performance", "statement": "must be fast",
             "source_refs": [{"ref": "doc:x@abc#perf", "trust_level": "EXTERNAL_UNSTRUCTURED"}]}]}),
            encoding="utf-8")
        res = run(self.base("--start", "ARCHITECTURE"))[1]
        r = by_kind(res)["nfr-catalog"]
        self.assertEqual(r["outcome"], "BLOCK")
        self.assertIn("unquantified", r["missing"][0])

    def test_plan_requires_reviewed_architecture_and_approval_at_high(self):
        res = run(self.base("--start", "PLAN", "--tier", "HIGH"))[1]
        self.assertEqual(by_kind(res)["architecture-package"]["backfill_stage"], "ARCHITECTURE")
        arch = self.planning / "architecture"
        arch.mkdir()
        (arch / "README.md").write_text("# Solution architecture", encoding="utf-8")
        (arch / "service-map.yaml").write_text("{}", encoding="utf-8")
        ev = self.root / "ev.json"
        ev.write_text(json.dumps({"reviews": [{"item": "architecture_review", "role": "architect",
                                               "actor_type": "SYSTEM", "lifecycle_state": "VERIFIED",
                                               "verdict": "ACCEPT"}]}), encoding="utf-8")
        r = by_kind(run(self.base("--start", "PLAN", "--tier", "HIGH", "--evidence", str(ev)))[1])["architecture-package"]
        self.assertEqual(r["outcome"], "BLOCK")
        self.assertEqual(len(r["missing"]), 2)  # SYSTEM review doesn't count + no human approval
        ev.write_text(json.dumps({"reviews": [{"item": "architecture_review", "role": "architect",
                                               "actor_type": "AGENT", "lifecycle_state": "REVIEWED",
                                               "verdict": "ACCEPT"}],
                                  "approvals": [{"item": "architecture_approval", "approver": "human:tech-lead",
                                                 "actor_type": "HUMAN"}]}), encoding="utf-8")
        r = by_kind(run(self.base("--start", "PLAN", "--tier", "HIGH", "--evidence", str(ev)))[1])["architecture-package"]
        self.assertEqual(r["outcome"], "SATISFIED")

    def test_plan_low_tier_does_not_need_architecture(self):
        res = run(self.base("--start", "PLAN", "--tier", "LOW"))[1]
        self.assertIn("not required", by_kind(res)["architecture-package"]["detail"])

    # ---------------------------------------------------------------- workspace / errors
    def test_missing_repo_role_asks_with_create_options(self):
        ws = self._workspace(app={"status": "MISSING", "options": ["a", "b", "c"]})
        self.ws = ws
        res = run(self.base("--start", "IMPLEMENT", "--story", "ST-1", "--evidence", str(self.evidence)))[1]
        r = by_kind(res)["repo:app"]
        self.assertEqual(r["outcome"], "ASK")
        self.assertEqual(r["options"], ["a", "b", "c"])

    def test_range_errors_and_observed_stages(self):
        code, res = run(self.base("--start", "PLAN", "--end", "INTAKE"))
        self.assertEqual(code, 2)
        self.scan_conventions()
        res = run(self.base("--start", "IMPLEMENT", "--end", "RELEASE", "--story", "ST-1",
                            "--evidence", str(self.evidence)))[1]
        self.assertEqual(res["observed_only_in_range"], ["INTEGRATE", "RELEASE"])


class StagesFileTest(unittest.TestCase):
    def test_stages_yaml_matches_schema_and_checks_exist(self):
        stages = sp.wl.load_stages()
        schema = json.loads((REPO / "skills/workflow/stages.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(sp.wl.validate(stages, schema), [])
        self.assertEqual(stages["order"], sp.wl.STAGES)
        for name, st in stages["stages"].items():
            for inp in st["inputs"]:
                self.assertIn(inp["kind"], sp.CHECKS, f"{name}: no check for {inp['kind']}")
                self.assertIn(inp["kind"], stages["artifact_kinds"])
            for gate in st["exit_gate"]:
                if gate["kind"] == "script" and "test-integrity" not in gate["ref"]:
                    self.assertTrue((REPO / gate["ref"]).is_file(), gate["ref"])


if __name__ == "__main__":
    unittest.main()
