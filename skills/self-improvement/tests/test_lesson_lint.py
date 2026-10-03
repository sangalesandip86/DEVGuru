"""Tests for scripts/lesson_lint.py."""
from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lesson_lint  # noqa: E402

SKILL_MD = """---
name: story-writer
metadata:
  stage: PLAN
---

# Story Writer

## Purpose
Write stories.

## Procedure
1. Read the requirement and its source refs.
2. Split into stories.
3. Size each story.
4. Write acceptance criteria in Given/When/Then form,
   one criterion per behavior.
5. Record traceability.

## Outputs
Stories.
"""

GOOD = {
    "lesson_id": "LES-14",
    "skill": "product-planning/story-writer",
    "step": "Procedure 4 — write acceptance criteria",
    "failure_class": "MISSING_NEGATIVE_CASE",
    "occurrences": {"incidents": 7, "change_sets": 4, "projects": 2},
    "what_failed": "AC for input-validation stories covered only valid input",
    "advice": "When a story changes input handling, require ≥1 negative AC per validated field",
    "check": "touches.input_validation → count(ac.kind == negative) ≥ 1",
    "remedy_kind": "GATE",
    "remedy_target": {"location": "skills/product-planning/policies/dor-policy.yaml#negative_ac"},
    "repro": {"evals_path": "evals/story-writer/evals.json", "eval_id": 3,
              "fails_on_current": None, "passes_on_revision": None},
    "last_fired": "2026-09-20",
    "scope": "PROJECT",
    "status": "DRAFT",
    "sanitization": {"result": "NOT_RUN", "checked_at": None},
}


class LessonLintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.catalog = Path(cls.tmp.name)
        d = cls.catalog / "product-planning" / "story-writer"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        cls.schema = lesson_lint.load_schema(lesson_lint.SCHEMA)
        cls.classes = json.loads(lesson_lint.CLASS_MAP.read_text(encoding="utf-8"))["classes"]
        cls.today = lesson_lint.dt.date(2026, 10, 3)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def lint(self, **changes):
        lesson = copy.deepcopy(GOOD)
        for k, v in changes.items():
            if v is None:
                lesson.pop(k, None)
            else:
                lesson[k] = v
        return lesson_lint.lint(lesson, self.catalog, self.classes, self.schema, self.today)

    def test_good_lesson_passes(self):
        errors, warnings = self.lint()
        self.assertEqual(errors, [])
        self.assertTrue(any("repro evals file not found" in w for w in warnings))  # DRAFT: warning only

    def test_unknown_skill_rejected(self):
        errors, _ = self.lint(skill="product-planning/no-such-skill")
        self.assertTrue(any("not found in catalog" in e for e in errors))

    def test_step_must_exist(self):
        errors, _ = self.lint(step="Procedure 9 — write acceptance criteria")
        self.assertTrue(any("no numbered step 9" in e for e in errors))

    def test_step_text_must_match_item(self):
        errors, _ = self.lint(step="Procedure 4 — deploy the database")
        self.assertTrue(any("does not match" in e for e in errors))

    def test_heading_step_accepted(self):
        errors, _ = self.lint(step="Outputs")
        self.assertEqual(errors, [])

    def test_class_must_be_in_taxonomy(self):
        errors, _ = self.lint(failure_class="SOMETHING_ELSE")
        self.assertTrue(any("taxonomy" in e for e in errors))

    def test_vague_advice_rejected(self):
        for advice in ("Be careful with validation in stories",
                       "Make sure to consider edge cases when writing AC",
                       "Write better acceptance criteria for stories"):
            errors, _ = self.lint(advice=advice)
            self.assertTrue(errors, advice)

    def test_gate_needs_check(self):
        errors, _ = self.lint(check=None)
        self.assertTrue(any("needs a mechanical `check`" in e for e in errors))

    def test_skill_text_with_check_warns_prefer_gate(self):
        errors, warnings = self.lint(remedy_kind="SKILL_TEXT", remedy_target={
            "location": "SKILL.md#Procedure", "replaces_or_merges": "Procedure step 4"})
        self.assertEqual(errors, [])
        self.assertTrue(any("prefer GATE/LINT" in w for w in warnings))

    def test_skill_text_needs_replace_or_merge(self):
        errors, _ = self.lint(remedy_kind="SKILL_TEXT", remedy_target={"location": "SKILL.md#Procedure"})
        self.assertTrue(any("replaces_or_merges" in e for e in errors))

    def test_org_scope_requires_approved(self):
        errors, _ = self.lint(scope="ORG")
        self.assertTrue(any("status" in e or "approved_by" in e for e in errors))

    def test_prune_candidate_warning(self):
        _, warnings = self.lint(last_fired="2026-01-01")
        self.assertTrue(any("PRUNE_CANDIDATE" in w for w in warnings))

    def test_free_text_fields_rejected(self):
        errors, _ = self.lint(prompt="the real customer task")
        self.assertTrue(any("unexpected field 'prompt'" in e for e in errors))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            good, bad = Path(t, "good.json"), Path(t, "bad.json")
            good.write_text(json.dumps(GOOD), encoding="utf-8")
            bad.write_text(json.dumps({**GOOD, "advice": "be careful"}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(lesson_lint.main([str(good), "--catalog", str(self.catalog), "--today", "2026-10-03"]), 0)
                self.assertEqual(lesson_lint.main([str(bad), "--catalog", str(self.catalog)]), 1)

    def test_yaml_lesson_loads(self):
        with tempfile.TemporaryDirectory() as t:
            y = Path(t, "l.yaml")
            y.write_text("lesson_id: LES-1\nskill: product-planning/story-writer\n", encoding="utf-8")
            self.assertEqual(lesson_lint.load_doc(y)["lesson_id"], "LES-1")


if __name__ == "__main__":
    unittest.main()
