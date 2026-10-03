"""Drift guard: every real check ID in the repo is mapped, and the schemas agree with the taxonomy."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SI = HERE.parent
REPO = SI.parents[1]
sys.path.insert(0, str(SI / "scripts"))
from _schema_lite import validate  # noqa: E402

MAP = json.loads((SI / "failure-capture/reference/failure-class-map.json").read_text(encoding="utf-8"))
TAXONOMY = (SI / "failure-capture/reference/failure-taxonomy.md").read_text(encoding="utf-8")
INCIDENT_SCHEMA = json.loads((SI / "failure-capture/reference/incident.schema.json").read_text(encoding="utf-8"))
LESSON_SCHEMA = json.loads((SI / "improvement-review/reference/lesson.schema.json").read_text(encoding="utf-8"))
POLICIES = REPO / "skills/product-planning/policies"
TI = REPO / "skills/enforcement/ci-checks/test-integrity"


def policy_ids(name: str) -> set[str]:
    p = POLICIES / name
    return set(re.findall(r"^\s*- id:\s*([\w-]+)", p.read_text(encoding="utf-8"), re.M)) if p.is_file() else set()


class FailureClassMapTest(unittest.TestCase):
    def test_classes_match_taxonomy_and_schemas(self):
        classes = MAP["classes"]
        documented = re.findall(r"^\| \d+ \| `([A-Z_]+)` \|", TAXONOMY, re.M)
        self.assertEqual(classes, documented)
        self.assertEqual(set(INCIDENT_SCHEMA["properties"]["failure_class"]["enum"]) - {None}, set(classes))
        self.assertEqual(set(LESSON_SCHEMA["properties"]["failure_class"]["enum"]), set(classes))

    def test_every_mapping_targets_a_class(self):
        for key, v in MAP["map"].items():
            self.assertTrue(v["class"] is None or v["class"] in MAP["classes"], key)
            self.assertRegex(key, r"^[a-z-]+:[A-Za-z0-9_.-]+$")

    def test_all_dor_dod_items_mapped(self):
        for prefix, name in (("dor", "dor-policy.yaml"), ("dod", "dod-policy.yaml")):
            missing = {i for i in policy_ids(name) if f"{prefix}:{i}" not in MAP["map"]}
            self.assertFalse(missing, f"{name} items not in failure-class-map.json: {sorted(missing)}")

    def test_all_integrity_codes_mapped(self):
        guard = TI / "test_integrity_guard.py"
        if guard.is_file():
            codes = set(re.findall(r'"([A-Z][A-Z_]{5,})"', guard.read_text(encoding="utf-8"))) - {"FACT", "FAIL", "PASS"}
            missing = {c for c in codes if f"test-integrity:{c}" not in MAP["map"]}
            self.assertFalse(missing, f"test-integrity codes not mapped: {sorted(missing)}")
        sleep = TI / "no_fixed_sleep_check.py"
        if sleep.is_file():
            rules = set(re.findall(r'^\s*\("([a-z]+-[a-z0-9-]+)",', sleep.read_text(encoding="utf-8"), re.M))
            missing = {r for r in rules if f"no-fixed-sleep:{r}" not in MAP["map"]}
            self.assertFalse(missing, f"no-fixed-sleep rules not mapped: {sorted(missing)}")

    def test_adr_examples(self):
        self.assertEqual(MAP["map"]["dor:negative_ac"]["class"], "MISSING_NEGATIVE_CASE")
        self.assertEqual(MAP["map"]["test-integrity:ASSERTION_REMOVED"]["class"], "WEAKENED_TEST")
        self.assertEqual(MAP["map"]["failure-mode:SCOPE_VIOLATION"]["class"], "SCOPE_CREEP")
        self.assertEqual(MAP["map"]["dependency-decision:missing_decision"]["class"], "UNDECLARED_DEVIATION")


BASE_INCIDENT = {
    "incident_id": "INC-a1b2c3", "signal_type": "negative", "signal_source": "REVIEWER",
    "skill": "product-planning/story-writer", "step": "Procedure 4 — write acceptance criteria",
    "failure_class": "MISSING_NEGATIVE_CASE", "check_id": "dor:negative_ac", "agent_role": "product-planner",
    "verification_strength": {"changed_code_coverage": None, "acceptance_criteria_exercised": False},
    "pattern_eligible": True, "evidence_refs": ["ENTRY-3f9c2ab01d4e"], "platform_release_sha": "a1b2c3d",
    "recorded_at": "2026-10-03T10:00:00Z", "status": "OPEN",
}


class IncidentSchemaTest(unittest.TestCase):
    def errs(self, **changes):
        inc = {**BASE_INCIDENT, **changes}
        return validate({k: v for k, v in inc.items() if v != "__drop__"}, INCIDENT_SCHEMA)

    def test_valid(self):
        self.assertEqual(self.errs(), [])

    def test_no_use_case_fields(self):
        for field in ("prompt", "files", "expected_output", "change_set_id"):
            self.assertTrue(self.errs(**{field: "x"}), field)

    def test_evidence_refs_are_ledger_ids_only(self):
        self.assertTrue(self.errs(evidence_refs=["repo@abc1234:src/x.py"]))

    def test_judgment_only_needs_note_by_other_role(self):
        self.assertTrue(self.errs(check_id=None, failure_class="DESIGN_DEFECT"))
        ok = dict(check_id=None, failure_class="DESIGN_DEFECT", note="Duplicated validation logic across layers",
                  note_author_role="code-reviewer",
                  note_sanitize={"result": "PASS", "checked_at": "2026-10-03T10:00:00Z"})
        self.assertEqual(self.errs(**ok), [])
        self.assertTrue(any("must differ" in e for e in self.errs(**{**ok, "note_author_role": "product-planner"})))

    def test_note_length_capped(self):
        self.assertTrue(self.errs(note="x" * 281, note_author_role="human:tech-lead",
                                  note_sanitize={"result": "PASS", "checked_at": "2026-10-03T10:00:00Z"}))

    def test_unverified_positive_not_eligible(self):
        self.assertTrue(self.errs(signal_type="unverified-positive", failure_class=None, check_id="__drop__"))
        self.assertEqual(self.errs(signal_type="unverified-positive", failure_class=None, check_id="__drop__",
                                   pattern_eligible=False), [])


if __name__ == "__main__":
    unittest.main()
