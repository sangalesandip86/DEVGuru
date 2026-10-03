"""Tests for the planning gates (plan v3.1 §4.12). Stdlib unittest only.

Run:  python -m unittest discover -s skills/enforcement/ci-checks/planning-gates/tests -v
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATES = HERE.parent
sys.path.insert(0, str(GATES))

import ac_coverage  # noqa: E402
import completion_gate  # noqa: E402
import minyaml  # noqa: E402
import plan_lint  # noqa: E402
import planning_lib as pl  # noqa: E402
import readiness_gate  # noqa: E402
from ac_hash import ac_hash  # noqa: E402

REPO = GATES.parents[3]
EXAMPLE = REPO / "examples" / "plans"
NOW = pl._parse_ts("2026-10-20T09:00:00Z")

REQ = {"id": "REQ-1", "title": "Req", "statement": "A sufficiently long statement.",
       "requested_by": "someone", "business_outcome": "Outcome stated",
       "source_refs": [{"ref": "https://x/1", "trust_level": "EXTERNAL_UNSTRUCTURED"}]}


def story(**over) -> dict:
    s = {
        "id": "ST-1", "title": "A story", "type": "FEATURE_STORY",
        "objective": "Do the thing", "persona": "PM", "value_statement": "so that value",
        "requirement_id": "REQ-1", "scope": ["thing"], "out_of_scope": [],
        "affected_paths": ["app/feature/**"],
        "acceptance_criteria": [
            {"id": "ST-1/AC-1", "given": "a user", "when": "they act", "then": "it works",
             "kind": "functional", "verification": "automated"},
            {"id": "ST-1/AC-2", "given": "bad input", "when": "they act", "then": "an error shows",
             "kind": "negative", "verification": "automated"},
        ],
        "touches": {"ui": False, "api_contracts": [], "data_migration": False, "infra": False},
        "data_classification": "INTERNAL", "size": "S",
        "source_refs": [{"ref": "https://x/1", "trust_level": "EXTERNAL_UNSTRUCTURED"}],
    }
    s.update(over)
    return s


def review(s: dict, item: str, role: str, actor="AGENT", verdict="ACCEPT", state="REVIEWED", **extra):
    r = {"story": s["id"], "item": item, "role": role, "actor_type": actor, "verdict": verdict,
         "lifecycle_state": state, "ac_hash": ac_hash(s)}
    r.update(extra)
    return r


def ready_evidence(s: dict) -> dict:
    return {"reviews": [review(s, "qa_testability", "qa-derive"),
                        review(s, "developer_feasibility", "developer")]}


class PlanDir:
    def __init__(self, stories: list[dict], extra: dict | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.write("requirements", REQ)
        for s in stories:
            self.write("stories", s)
        for kind, docs in (extra or {}).items():
            for d in docs:
                self.write(kind, d)

    def write(self, kind: str, doc: dict) -> None:
        d = self.path / kind
        d.mkdir(exist_ok=True)
        # JSON is a valid document for the YAML-subset loader
        (d / f"{doc['id']}.yaml").write_text(json.dumps(doc), encoding="utf-8")

    def __enter__(self):
        return self.path

    def __exit__(self, *a):
        self.tmp.cleanup()


def items(result: dict) -> dict:
    return {i["id"]: i for i in result["items"]}


class MinYamlTest(unittest.TestCase):
    def test_subset(self):
        doc = minyaml.loads(
            "# c\nid: ST-1\nlist:\n  - a\n  - key: v\n    other: [x, 'y z', 3]\nflag: true\n"
            "text: >\n  folded\n  line\nquoted: \"a: b # not comment\"  # comment\nnone: ~\n")
        self.assertEqual(doc["list"], ["a", {"key": "v", "other": ["x", "y z", 3]}])
        self.assertEqual(doc["text"], "folded line\n")
        self.assertEqual(doc["quoted"], "a: b # not comment")
        self.assertIs(doc["flag"], True)
        self.assertIsNone(doc["none"])

    def test_unsupported_raises(self):
        with self.assertRaises(minyaml.YamlSubsetError):
            minyaml.loads("a: &anchor 1\nb: *anchor\n")
        with self.assertRaises(minyaml.YamlSubsetError):
            minyaml.loads("a: 1\na: 2\n")

    def test_policies_parse(self):
        for name in ("story-types", "dor-policy", "dod-policy"):
            self.assertIsInstance(pl.load_policy(name), dict)


class JudgmentNeverStructuralTest(unittest.TestCase):
    def _qa_status(self, recs):
        s = story()
        ev = {"reviews": recs + [review(s, "developer_feasibility", "developer")]}
        with PlanDir([s]) as p:
            return items(readiness_gate.evaluate(p, "ST-1", ev, NOW))["qa_testability"]

    def test_system_actor_never_satisfies_judgment(self):
        s = story()
        st = self._qa_status([review(s, "qa_testability", "qa-derive", actor="SYSTEM", state="VERIFIED")])
        self.assertEqual(st["status"], pl.MISSING)
        self.assertIn("SYSTEM", st["detail"])

    def test_verified_lifecycle_never_satisfies_judgment(self):
        s = story()
        st = self._qa_status([review(s, "qa_testability", "qa-derive", state="VERIFIED")])
        self.assertEqual(st["status"], pl.MISSING)

    def test_wrong_role_does_not_count(self):
        s = story()
        st = self._qa_status([review(s, "qa_testability", "developer")])
        self.assertEqual(st["status"], pl.MISSING)

    def test_human_and_right_role_count(self):
        s = story()
        self.assertEqual(self._qa_status([review(s, "qa_testability", "qa-derive")])["status"], pl.PASS)
        self.assertEqual(self._qa_status([review(s, "qa_testability", "x", actor="HUMAN")])["status"], pl.PASS)

    def test_reject_blocks(self):
        s = story()
        st = self._qa_status([review(s, "qa_testability", "qa-derive", verdict="REJECT")])
        self.assertEqual(st["status"], pl.REJECTED)

    def test_structurally_perfect_story_without_reviews_is_not_ready(self):
        with PlanDir([story()]) as p:
            r = readiness_gate.evaluate(p, "ST-1", {}, NOW)
        self.assertEqual(r["result"], "NOT_READY")
        failing = {i["id"] for i in r["items"] if i["status"] != pl.PASS}
        self.assertEqual(failing, {"qa_testability", "developer_feasibility"})

    def test_approval_requires_human(self):
        s = story(type="API_CONTRACT", touches={"api_contracts": ["c.v1"]}, nfrs=["p95 < 300 ms at 200 RPS"])
        ev = ready_evidence(s)
        ev["reviews"].append(review(s, "architect_contract_review", "architect"))
        ev["approvals"] = [{"story": "ST-1", "item": "scope_approval", "approver": "human:product-owner",
                            "actor_type": "AGENT"}]
        with PlanDir([s]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ev, NOW)
            self.assertEqual(items(r)["scope_approval"]["status"], pl.MISSING)
            ev["approvals"][0]["actor_type"] = "HUMAN"
            r = readiness_gate.evaluate(p, "ST-1", ev, NOW)
        self.assertEqual(r["result"], "READY", [i for i in r["items"] if i["status"] != "PASS"])


class AcFreezeTest(unittest.TestCase):
    def test_lint_reports_requires_refining(self):
        s = story()
        recorded = ac_hash(s)
        changed = copy.deepcopy(s)
        changed["acceptance_criteria"][0]["then"] = "it works differently"
        with PlanDir([changed]) as p:
            out = plan_lint.lint(p, {"ST-1": {"status": "IN_PROGRESS", "ac_hash": recorded}})
        self.assertEqual(out["errors"], [])
        self.assertEqual(len(out["freeze_violations"]), 1)
        self.assertEqual(out["freeze_violations"][0]["action"], "REQUIRES_REFINING")

    def test_reformatting_does_not_trip_freeze(self):
        s = story()
        reformatted = copy.deepcopy(s)
        reformatted["acceptance_criteria"].reverse()
        reformatted["acceptance_criteria"][0]["then"] = "  an   error\nshows "
        self.assertEqual(ac_hash(s), ac_hash(reformatted))

    def test_stale_review_no_longer_counts(self):
        s = story()
        ev = ready_evidence(s)
        changed = copy.deepcopy(s)
        changed["acceptance_criteria"][0]["then"] = "it works differently"
        with PlanDir([changed]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ev, NOW)
        st = items(r)["qa_testability"]
        self.assertEqual(st["status"], pl.MISSING)
        self.assertIn("stale AC hash", st["detail"])

    def test_done_requires_ready_at_current_hash(self):
        s = story()
        changed = copy.deepcopy(s)
        changed["acceptance_criteria"][0]["then"] = "it works differently"
        ev = {"readiness": {"ST-1": {"status": "IN_VERIFICATION", "ac_hash": ac_hash(s)}}}
        with PlanDir([changed]) as p:
            r = completion_gate.evaluate(p, "ST-1", ev, None, NOW)
        self.assertEqual(items(r)["ready_at_current_ac"]["status"], pl.FAIL)
        self.assertEqual(r["result"], "NOT_DONE")


class TierFloorTest(unittest.TestCase):
    types = pl.load_policy("story-types")

    def test_floor_raises(self):
        t = pl.effective_tier(story(type="API_CONTRACT", risk_tier="LOW", affected_paths=["app/x/**"]), self.types)
        self.assertEqual(t["tier"], "HIGH")

    def test_low_floor_never_lowers(self):
        t = pl.effective_tier(story(type="DOCUMENTATION", affected_paths=["services/payments/fees.py"]), self.types)
        self.assertEqual(t["tier"], "HIGH")
        t = pl.effective_tier(story(type="DOCUMENTATION", risk_tier="CRITICAL", affected_paths=["docs/a.md"]), self.types)
        self.assertEqual(t["tier"], "CRITICAL")

    def test_uncomputable_is_high(self):
        t = pl.effective_tier(story(type="FEATURE_STORY", affected_paths=[]), self.types)
        self.assertEqual(t["tier"], "HIGH")
        self.assertTrue(t["fail_safe"])

    def test_high_tier_adds_approval_and_nfrs(self):
        s = story(affected_paths=["services/payments/x.py"])
        with PlanDir([s]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ready_evidence(s), NOW)
        it = items(r)
        self.assertEqual(it["scope_approval"]["status"], pl.MISSING)
        self.assertEqual(it["nfrs_identified"]["status"], pl.MISSING)


class SizeAndNegativeAcTest(unittest.TestCase):
    def test_size_l_blocks_ready(self):
        s = story(size="L")
        with PlanDir([s]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ready_evidence(s), NOW)
        self.assertEqual(r["result"], "NOT_READY")
        self.assertEqual(items(r)["size_ok"]["status"], pl.FAIL)

    def test_missing_negative_ac_fails(self):
        s = story()
        s["acceptance_criteria"] = s["acceptance_criteria"][:1]
        with PlanDir([s]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ready_evidence(s), NOW)
        self.assertEqual(r["result"], "NOT_READY")
        self.assertEqual(items(r)["negative_ac"]["status"], pl.MISSING)

    def test_documentation_exempt_from_negative_ac(self):
        s = story(type="DOCUMENTATION", affected_paths=["docs/guide.md"])
        s["acceptance_criteria"] = s["acceptance_criteria"][:1]
        ev = {"reviews": [review(s, "developer_feasibility", "developer")]}
        with PlanDir([s]) as p:
            r = readiness_gate.evaluate(p, "ST-1", ev, NOW)
        self.assertIn("negative_ac", r["not_applicable"])
        self.assertEqual(r["result"], "READY", [i for i in r["items"] if i["status"] != "PASS"])

    def test_status_field_is_rejected(self):
        s = story(status="READY")
        with PlanDir([s]) as p:
            out = plan_lint.lint(p)
            r = readiness_gate.evaluate(p, "ST-1", ready_evidence(s), NOW)
        self.assertTrue(any("status" in e["error"] for e in out["errors"]))
        self.assertEqual(items(r)["schema_valid"]["status"], pl.FAIL)


class SpikeDodTest(unittest.TestCase):
    def _spike(self):
        return story(id="ST-5", type="SPIKE", acceptance_criteria=[], affected_paths=["docs/adr/**"],
                     spike={"question": "Which option is faster?", "timebox_days": 2})

    def _evidence(self, s, paths):
        return {"readiness": {"ST-5": {"status": "IN_PROGRESS", "ac_hash": ac_hash(s)}},
                "change_sets": [{"id": "CS-1", "story_refs": ["ST-5"], "status": "INTEGRATED",
                                 "changed_paths": paths}],
                "decisions": [{"story": "ST-5", "adr_ref": "repo@abc:docs/adr/0001.md"}]}

    def test_spike_done_with_adr_and_follow_up(self):
        s = self._spike()
        follow = story(id="ST-6", follow_up_of="ST-5", acceptance_criteria=[
            {"id": "ST-6/AC-1", "given": "g g", "when": "w w", "then": "t t", "kind": "functional",
             "verification": "automated"}])
        with PlanDir([s, follow]) as p:
            r = completion_gate.evaluate(p, "ST-5", self._evidence(s, ["docs/adr/0001.md"]), None, NOW)
        self.assertEqual(r["variant"], "spike")
        self.assertEqual(r["result"], "DONE", [i for i in r["items"] if i["status"] != "PASS"])

    def test_spike_with_production_code_is_not_done(self):
        s = self._spike()
        follow = story(id="ST-6", follow_up_of="ST-5", acceptance_criteria=[
            {"id": "ST-6/AC-1", "given": "g g", "when": "w w", "then": "t t", "kind": "functional",
             "verification": "automated"}])
        with PlanDir([s, follow]) as p:
            r = completion_gate.evaluate(p, "ST-5", self._evidence(s, ["src/engine/fast.py"]), None, NOW)
        self.assertEqual(items(r)["spike_no_production_code"]["status"], pl.FAIL)
        self.assertEqual(r["result"], "NOT_DONE")

    def test_spike_without_follow_up_is_not_done(self):
        s = self._spike()
        with PlanDir([s]) as p:
            r = completion_gate.evaluate(p, "ST-5", self._evidence(s, ["docs/adr/0001.md"]), None, NOW)
        self.assertEqual(items(r)["spike_follow_ups"]["status"], pl.MISSING)


class CoverageTest(unittest.TestCase):
    def test_failing_and_not_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "test_x.py").write_text(
                "# @ac ST-1/AC-1\ndef test_ok():\n    pass\n\n"
                "def test_bad():\n    '''@ac ST-1/AC-2'''\n    pass\n\n"
                "# @ac ST-1/AC-3\ndef test_never_run():\n    pass\n", encoding="utf-8")
            (d / "r.xml").write_text(
                '<testsuite><testcase name="test_ok"/><testcase name="test_bad"><failure/></testcase>'
                '</testsuite>', encoding="utf-8")
            out = ac_coverage.coverage([d / "test_x.py"], [d / "r.xml"])
        acs = out["acceptance_criteria"]
        self.assertTrue(acs["ST-1/AC-1"]["passing"])
        self.assertFalse(acs["ST-1/AC-2"]["passing"])
        self.assertEqual(acs["ST-1/AC-3"]["results"]["test_never_run"], "NOT_RUN")
        self.assertFalse(acs["ST-1/AC-3"]["passing"])

    def test_characterization_never_counts_as_ac_verification(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "test_x.py").write_text(
                "# @characterization @ac ST-1/AC-1\ndef test_pins_legacy():\n    pass\n", encoding="utf-8")
            (d / "r.xml").write_text(
                '<testsuite><testcase name="test_pins_legacy"/></testsuite>', encoding="utf-8")
            out = ac_coverage.coverage([d / "test_x.py"], [d / "r.xml"])
        self.assertNotIn("ST-1/AC-1", out["acceptance_criteria"])
        self.assertEqual(out["excluded_characterization_tests"], ["test_pins_legacy"])


class ChangedAcTest(unittest.TestCase):
    def test_only_semantically_changed_acs_are_listed(self):
        import plan_lint
        with tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as h:
            for root, then2 in ((Path(b), "an error is shown"), (Path(h), "a validation error is shown")):
                (root / "stories").mkdir()
                (root / "stories" / "ST-1.yaml").write_text(
                    '{"acceptance_criteria": ['
                    '{"id": "ST-1/AC-1", "given": "g", "when": "w", "then": "t", "kind": "functional"},'
                    '{"id": "ST-1/AC-2", "given": "g", "when": "w", "then": "%s", "kind": "negative"}]}' % then2,
                    encoding="utf-8")
            self.assertEqual(plan_lint.changed_acs(Path(b), Path(h)), ["ST-1/AC-2"])


class WorkedExampleTest(unittest.TestCase):
    """Guards the expected output documented in examples/plans/README.md."""

    @classmethod
    def setUpClass(cls):
        cls.ev = json.loads((EXAMPLE / "evidence" / "evidence.json").read_text(encoding="utf-8"))

    def test_lint_clean(self):
        out = plan_lint.lint(EXAMPLE, self.ev["readiness"])
        self.assertEqual(out["errors"], [])
        self.assertEqual(out["freeze_violations"], [])

    def test_readiness(self):
        expected = {"ST-1": "READY", "ST-2": "NOT_READY", "ST-3": "READY", "ST-4": "NOT_READY"}
        for sid, want in expected.items():
            self.assertEqual(readiness_gate.evaluate(EXAMPLE, sid, self.ev, NOW)["result"], want, sid)
        st2 = readiness_gate.evaluate(EXAMPLE, "ST-2", self.ev, NOW)
        self.assertEqual({i["id"] for i in st2["items"] if i["status"] != pl.PASS},
                         {"qa_testability", "architect_contract_review", "scope_approval"})

    def test_completion(self):
        cov = ac_coverage.coverage([EXAMPLE / "evidence" / "tests"], [EXAMPLE / "evidence" / "junit.xml"],
                                   EXAMPLE, "ST-1")
        st1 = completion_gate.evaluate(EXAMPLE, "ST-1", self.ev, cov, NOW)
        self.assertEqual((st1["result"], st1["awaiting_acceptance"]), ("DONE", True))
        st3 = completion_gate.evaluate(EXAMPLE, "ST-3", self.ev, None, NOW)
        self.assertEqual((st3["result"], st3["variant"]), ("DONE", "spike"))


if __name__ == "__main__":
    unittest.main()
