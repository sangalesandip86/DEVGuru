"""Layer B: Handoff Contract Tests — pipeline stage coverage and routing completeness.

Validates that:
  1. Every stage input (from stages.yaml) is produced by some upstream stage's outputs.
  2. Every stage has at least one skill with outputs (no dead stage).
  3. SKILL.md frontmatter inputs/outputs use only valid artifact kinds.
  4. Skill-router STORY_TYPE_BINDINGS cover the canonical story-type vocabulary.
  5. Handoff payload schema patterns are consistent.

No LLM calls — pure metadata/schema validation.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
STAGES_YAML = SKILLS_DIR / "workflow" / "stages.yaml"
CONVENTIONS = REPO_ROOT / "docs" / "authoring-conventions.md"
ROUTE_PY = SKILLS_DIR / "skill-routing" / "skill-router" / "scripts" / "route.py"
CM_DOMAIN = (SKILLS_DIR / "mcp-servers" / "adlc-mcp" / "src" / "adlc_mcp"
             / "modules" / "change_management" / "domain.py")


def _load_stages() -> dict:
    text = STAGES_YAML.read_text(encoding="utf-8")
    return json.loads(text)


def _load_artifact_kinds() -> set[str]:
    text = CONVENTIONS.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("- Artifact kinds"):
            groups = re.findall(r"`([^`]+)`", line)
            if groups:
                return set(max(groups, key=len).split())
    raise ValueError("artifact kinds line not found in conventions")


def _load_story_types() -> set[str]:
    text = CONVENTIONS.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("- Story types:"):
            groups = re.findall(r"`([^`]+)`", line)
            if groups:
                return set(max(groups, key=len).split())
    raise ValueError("story types line not found in conventions")


def _parse_skill_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    block = m.group(1)
    meta = {}
    in_meta = False
    for line in block.splitlines():
        if line.startswith("metadata:"):
            in_meta = True
            continue
        if in_meta:
            if line.startswith("  ") and ":" in line:
                key, _, val = line.strip().partition(":")
                meta[key.strip()] = val.strip()
            elif line.strip() and not line.startswith(" "):
                in_meta = False
    return meta


def _parse_list(raw: str) -> list[str]:
    raw = raw.strip().strip("[]")
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _load_all_skill_metadata() -> list[dict]:
    results = []
    for f in sorted(SKILLS_DIR.rglob("SKILL.md")):
        meta = _parse_skill_frontmatter(f)
        if meta and "stage" in meta:
            results.append({
                "path": f.relative_to(REPO_ROOT).as_posix(),
                "stage": meta["stage"],
                "inputs": _parse_list(meta.get("inputs", "[]")),
                "outputs": _parse_list(meta.get("outputs", "[]")),
                "repo_roles": _parse_list(meta.get("repo_roles", "[]")),
            })
    return results


def _load_route_story_bindings() -> dict[str, tuple[list[str], str]]:
    """Extract STORY_TYPE_BINDINGS from route.py by reading the source."""
    text = ROUTE_PY.read_text(encoding="utf-8")
    m = re.search(r"STORY_TYPE_BINDINGS:\s*dict\[.*?\]\s*=\s*\{(.*?)\n\}", text, re.S)
    if not m:
        raise ValueError("STORY_TYPE_BINDINGS not found in route.py")
    bindings = {}
    for match in re.finditer(r'"(\w+)":\s*\(', m.group(1)):
        bindings[match.group(1)] = True
    return bindings


class HandoffCoverageTest(unittest.TestCase):
    """Validate that every stage's required inputs are produced by upstream stages."""

    @classmethod
    def setUpClass(cls):
        cls.stages_data = _load_stages()
        cls.stage_order = cls.stages_data["order"]
        cls.stages = cls.stages_data["stages"]
        cls.artifact_kinds = _load_artifact_kinds()
        cls.skill_metadata = _load_all_skill_metadata()

    def test_stages_yaml_artifact_kinds_in_conventions(self):
        """Every artifact_kind defined in stages.yaml is in the conventions vocabulary."""
        yaml_kinds = set(self.stages_data.get("artifact_kinds", {}).keys())
        missing = yaml_kinds - self.artifact_kinds
        self.assertEqual(missing, set(),
                         f"stages.yaml artifact_kinds not in conventions: {sorted(missing)}")

    def test_stage_inputs_are_valid_artifact_kinds(self):
        """Every input.kind in stages.yaml is a known artifact kind."""
        for stage_name, stage in self.stages.items():
            for inp in stage.get("inputs", []):
                self.assertIn(inp["kind"], self.artifact_kinds,
                              f"{stage_name} input {inp['kind']!r} not a valid artifact kind")

    def test_stage_outputs_are_valid_artifact_kinds(self):
        """Every output in stages.yaml is a known artifact kind."""
        for stage_name, stage in self.stages.items():
            for out in stage.get("outputs", []):
                self.assertIn(out, self.artifact_kinds,
                              f"{stage_name} output {out!r} not a valid artifact kind")

    def test_required_inputs_produced_by_upstream(self):
        """Every 'always'-required input at stage N+1 is produced as output by some stage ≤ N.

        Inputs with required='never' or adopt_only=true are excluded — they're optional.
        Self-referential inputs (e.g. change-set at IMPLEMENT, which also outputs change-set)
        are excluded since the stage itself can produce them.
        """
        all_outputs = set()
        for stage_name in self.stage_order:
            stage = self.stages[stage_name]
            for inp in stage.get("inputs", []):
                required = inp.get("required", "always")
                if required == "never" or inp.get("adopt_only"):
                    continue
                kind = inp["kind"]
                stage_outputs = set(stage.get("outputs", []))
                if kind in stage_outputs:
                    continue
                if required == "always":
                    self.assertIn(kind, all_outputs,
                                  f"{stage_name} requires '{kind}' (always) but no upstream "
                                  f"stage produces it. Available: {sorted(all_outputs)}")
            all_outputs.update(stage.get("outputs", []))

    def test_skill_frontmatter_inputs_are_valid(self):
        """Every SKILL.md's inputs[] values are valid artifact kinds."""
        for skill in self.skill_metadata:
            for inp in skill["inputs"]:
                self.assertIn(inp, self.artifact_kinds,
                              f"{skill['path']} input '{inp}' not a valid artifact kind")

    def test_skill_frontmatter_outputs_are_valid(self):
        """Every SKILL.md's outputs[] values are valid artifact kinds."""
        for skill in self.skill_metadata:
            for out in skill["outputs"]:
                self.assertIn(out, self.artifact_kinds,
                              f"{skill['path']} output '{out}' not a valid artifact kind")

    def test_backfill_stages_are_valid(self):
        """Every backfill.default in stages.yaml points to a valid stage or special value."""
        valid_stages = set(self.stage_order) | {"RUN_CONVENTION_SCAN", "ASK"}
        for stage_name, stage in self.stages.items():
            for inp in stage.get("inputs", []):
                bf = inp.get("backfill", {})
                default = bf.get("default") if isinstance(bf, dict) else bf
                if default:
                    self.assertIn(default, valid_stages,
                                  f"{stage_name} input '{inp['kind']}' backfill "
                                  f"'{default}' not a valid stage")


class StageTransitionTest(unittest.TestCase):
    """Validate that every non-observed stage has skills and outputs."""

    @classmethod
    def setUpClass(cls):
        cls.stages_data = _load_stages()
        cls.stages = cls.stages_data["stages"]
        cls.stage_order = cls.stages_data["order"]
        cls.skill_metadata = _load_all_skill_metadata()

    def test_every_active_stage_has_skills_in_yaml(self):
        """Non-observed stages must list skills in stages.yaml."""
        for stage_name in self.stage_order:
            stage = self.stages[stage_name]
            if stage.get("observed_only"):
                continue
            self.assertTrue(
                len(stage.get("skills", [])) > 0,
                f"Stage {stage_name} is not observed-only but has no skills listed in stages.yaml")

    def test_every_non_observed_stage_has_skill_md_files(self):
        """Non-observed stages must have SKILL.md files with matching stage metadata."""
        stages_with_skills = set()
        for skill in self.skill_metadata:
            stages_with_skills.add(skill["stage"])

        for stage_name in self.stage_order:
            stage = self.stages[stage_name]
            if stage.get("observed_only"):
                continue
            self.assertIn(stage_name, stages_with_skills,
                          f"Stage {stage_name} has no SKILL.md files with stage={stage_name}")

    def test_every_non_observed_stage_produces_outputs(self):
        """Non-observed stages should produce at least one output in stages.yaml."""
        for stage_name in self.stage_order:
            stage = self.stages[stage_name]
            if stage.get("observed_only"):
                continue
            if stage_name == "LEARN":
                continue
            self.assertTrue(
                len(stage.get("outputs", [])) > 0,
                f"Stage {stage_name} is not observed-only but has no outputs")

    def test_observed_stages_have_no_lead_roles(self):
        """Observed-only stages (INTEGRATE, RELEASE) should have no lead roles."""
        for stage_name in self.stage_order:
            stage = self.stages[stage_name]
            if stage.get("observed_only"):
                self.assertEqual(
                    stage.get("lead_roles", []), [],
                    f"Observed stage {stage_name} should have no lead roles")

    def test_stage_order_is_complete(self):
        """stages.yaml order covers all defined stages."""
        defined = set(self.stages.keys())
        ordered = set(self.stage_order)
        self.assertEqual(defined, ordered,
                         f"Mismatch — defined: {sorted(defined)}, ordered: {sorted(ordered)}")


class RouteCompletenessTest(unittest.TestCase):
    """Validate that skill-router bindings cover the story-type vocabulary."""

    @classmethod
    def setUpClass(cls):
        cls.story_types = _load_story_types()
        cls.route_bindings = _load_route_story_bindings()

    def test_route_story_types_are_valid(self):
        """Every story type in STORY_TYPE_BINDINGS is a canonical story type."""
        for st in self.route_bindings:
            self.assertIn(st, self.story_types,
                          f"route.py STORY_TYPE_BINDINGS has unknown type '{st}'")

    def test_high_risk_types_have_bindings(self):
        """HIGH-risk story types (API_CONTRACT, DATA_MIGRATION, SECURITY_STORY) must have bindings."""
        high_risk = {"API_CONTRACT", "DATA_MIGRATION", "SECURITY_STORY"}
        for st in high_risk:
            self.assertIn(st, self.route_bindings,
                          f"HIGH-risk story type '{st}' has no skill-router binding")

    def test_always_mandatory_skills_exist(self):
        """Every skill listed in ALWAYS_MANDATORY exists as a SKILL.md."""
        text = ROUTE_PY.read_text(encoding="utf-8")
        m = re.search(r"ALWAYS_MANDATORY\s*=\s*\[(.*?)\]", text, re.S)
        self.assertIsNotNone(m, "ALWAYS_MANDATORY not found in route.py")
        skills = re.findall(r'"([^"]+)"', m.group(1))
        for skill in skills:
            skill_path = SKILLS_DIR / skill / "SKILL.md"
            self.assertTrue(skill_path.exists(),
                            f"ALWAYS_MANDATORY skill '{skill}' has no SKILL.md at {skill_path}")

    def test_story_type_binding_skills_exist(self):
        """Every skill referenced in STORY_TYPE_BINDINGS exists as a SKILL.md."""
        text = ROUTE_PY.read_text(encoding="utf-8")
        m = re.search(r"STORY_TYPE_BINDINGS:.*?\n\}", text, re.S)
        self.assertIsNotNone(m)
        skills = re.findall(r'"(\w+/[\w\-]+(?:/[\w\-]+)*)"', m.group(0))
        for skill in skills:
            skill_path = SKILLS_DIR / skill / "SKILL.md"
            self.assertTrue(skill_path.exists(),
                            f"STORY_TYPE_BINDINGS skill '{skill}' has no SKILL.md at {skill_path}")

    def test_stack_skill_map_skills_exist(self):
        """Every skill referenced in STACK_SKILL_MAP exists."""
        text = ROUTE_PY.read_text(encoding="utf-8")
        m = re.search(r"STACK_SKILL_MAP:.*?\n\}", text, re.S)
        self.assertIsNotNone(m)
        skills = set(re.findall(r'"(\w+/[\w\-]+(?:/[\w\-]+)*)"', m.group(0)))
        for skill in skills:
            skill_path = SKILLS_DIR / skill / "SKILL.md"
            self.assertTrue(skill_path.exists(),
                            f"STACK_SKILL_MAP skill '{skill}' has no SKILL.md at {skill_path}")


class HandoffSchemaConsistencyTest(unittest.TestCase):
    """Validate that handoff schema patterns in domain.py are consistent."""

    @classmethod
    def setUpClass(cls):
        cls.domain_text = CM_DOMAIN.read_text(encoding="utf-8")

    def test_artifact_ref_pattern_is_repo_at_sha_path(self):
        """ARTIFACT_REF pattern in domain.py should match repo@sha:path format."""
        m = re.search(r'ARTIFACT_REF\s*=\s*re\.compile\(r"([^"]+)"\)', self.domain_text)
        self.assertIsNotNone(m, "ARTIFACT_REF pattern not found in domain.py")
        pattern = m.group(1)
        compiled = re.compile(pattern)
        self.assertTrue(compiled.match("repo-a@a1b2c3d:docs/design.md"),
                        "ARTIFACT_REF should match 'repo@sha:path'")
        self.assertFalse(compiled.match("design.md"),
                         "ARTIFACT_REF should NOT match bare filenames")

    def test_content_hash_pattern_is_sha256(self):
        """CONTENT_HASH pattern should match sha256:<64 hex chars>."""
        m = re.search(r'CONTENT_HASH\s*=\s*re\.compile\(r"([^"]+)"\)', self.domain_text)
        self.assertIsNotNone(m, "CONTENT_HASH pattern not found in domain.py")
        pattern = m.group(1)
        compiled = re.compile(pattern)
        valid = "sha256:" + "ab" * 32
        self.assertTrue(compiled.match(valid),
                        f"CONTENT_HASH should match '{valid}'")
        self.assertFalse(compiled.match("md5:abc123"),
                         "CONTENT_HASH should NOT match non-sha256")

    def test_validate_handoff_payload_exists(self):
        """validate_handoff_payload function must exist in domain.py."""
        self.assertIn("def validate_handoff_payload", self.domain_text)

    def test_classifications_in_handoff_are_valid(self):
        """Classifications referenced in validate_handoff_payload must be from the vocabulary."""
        text = CONVENTIONS.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("- Classifications:"):
                groups = re.findall(r"`([^`]+)`", line)
                if groups:
                    vocab = set(max(groups, key=len).split())
                    break
        else:
            self.fail("Classifications line not found in conventions")

        m = re.search(r"def validate_handoff_payload.*?(?=\ndef |\Z)", self.domain_text, re.S)
        self.assertIsNotNone(m)
        fn_text = m.group(0)
        referenced = set(re.findall(r'"(QUESTION|ASSUMPTION|INFERENCE|FACT|DECISION|RISK|PROPOSAL)"', fn_text))
        for cls in referenced:
            self.assertIn(cls, vocab,
                          f"validate_handoff_payload references classification '{cls}' not in vocabulary")


if __name__ == "__main__":
    unittest.main()
