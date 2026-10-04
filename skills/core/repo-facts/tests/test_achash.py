"""Cross-check: shared ac_hash and work_planning domain.ac_hash produce identical results."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add repo-facts to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Add MCP src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "mcp-servers" / "adlc-mcp" / "src"))

from achash import ac_hash as shared_ac_hash  # noqa: E402
from adlc_mcp.modules.work_planning.domain import ac_hash as mcp_ac_hash  # noqa: E402

SAMPLE_STORY = {
    "id": "ST-1",
    "title": "User login",
    "acceptance_criteria": [
        {
            "id": "ST-1/AC-1",
            "given": "a registered user",
            "when": "they enter valid credentials",
            "then": "they are redirected to the dashboard",
            "kind": "functional",
            "verification": "automated",
            "tags": ["auth", "login"],
        },
        {
            "id": "ST-1/AC-2",
            "given": "a registered user",
            "when": "they enter invalid credentials",
            "then": "an error message is shown",
            "kind": "negative",
            "verification": "automated",
            "tags": ["auth"],
        },
    ],
}


class TestAcHashCrossCheck(unittest.TestCase):

    def test_shared_and_mcp_produce_identical_hash(self):
        shared = shared_ac_hash(SAMPLE_STORY)
        mcp = mcp_ac_hash(SAMPLE_STORY)
        self.assertEqual(shared, mcp, "shared ac_hash and MCP domain.ac_hash must agree")

    def test_reordering_acs_does_not_change_hash(self):
        reversed_story = dict(SAMPLE_STORY, acceptance_criteria=list(reversed(SAMPLE_STORY["acceptance_criteria"])))
        self.assertEqual(shared_ac_hash(SAMPLE_STORY), shared_ac_hash(reversed_story))
        self.assertEqual(mcp_ac_hash(SAMPLE_STORY), mcp_ac_hash(reversed_story))

    def test_whitespace_changes_do_not_change_hash(self):
        ws_story = {
            "acceptance_criteria": [
                {
                    "id": "ST-1/AC-1",
                    "given": "a   registered\n  user",
                    "when": "they  enter  valid   credentials",
                    "then": "they are redirected  to the  dashboard",
                    "kind": "functional",
                    "verification": "automated",
                    "tags": ["auth", "login"],
                },
            ],
        }
        clean_story = {
            "acceptance_criteria": [
                {
                    "id": "ST-1/AC-1",
                    "given": "a registered user",
                    "when": "they enter valid credentials",
                    "then": "they are redirected to the dashboard",
                    "kind": "functional",
                    "verification": "automated",
                    "tags": ["auth", "login"],
                },
            ],
        }
        self.assertEqual(shared_ac_hash(ws_story), shared_ac_hash(clean_story))
        self.assertEqual(mcp_ac_hash(ws_story), mcp_ac_hash(clean_story))

    def test_content_change_changes_hash(self):
        modified = {
            "acceptance_criteria": [
                dict(SAMPLE_STORY["acceptance_criteria"][0], then="they see a 404 page"),
                SAMPLE_STORY["acceptance_criteria"][1],
            ],
        }
        self.assertNotEqual(shared_ac_hash(SAMPLE_STORY), shared_ac_hash(modified))
        self.assertNotEqual(mcp_ac_hash(SAMPLE_STORY), mcp_ac_hash(modified))

    def test_extra_fields_ignored(self):
        """Non-semantic fields (notes, examples, priority) must not affect the hash."""
        with_extra = {
            "acceptance_criteria": [
                dict(SAMPLE_STORY["acceptance_criteria"][0], notes="some note", priority=1),
                dict(SAMPLE_STORY["acceptance_criteria"][1], examples=["ex1"]),
            ],
        }
        self.assertEqual(shared_ac_hash(SAMPLE_STORY), shared_ac_hash(with_extra))
        self.assertEqual(mcp_ac_hash(SAMPLE_STORY), mcp_ac_hash(with_extra))

    def test_empty_criteria(self):
        empty = {"acceptance_criteria": []}
        no_key = {}
        self.assertEqual(shared_ac_hash(empty), shared_ac_hash(no_key))
        self.assertEqual(mcp_ac_hash(empty), mcp_ac_hash(no_key))
        self.assertEqual(shared_ac_hash(empty), mcp_ac_hash(empty))

    def test_tag_order_does_not_matter(self):
        story_a = {"acceptance_criteria": [
            {"id": "ST-1/AC-1", "given": "x", "when": "y", "then": "z",
             "kind": "functional", "verification": "automated", "tags": ["b", "a"]},
        ]}
        story_b = {"acceptance_criteria": [
            {"id": "ST-1/AC-1", "given": "x", "when": "y", "then": "z",
             "kind": "functional", "verification": "automated", "tags": ["a", "b"]},
        ]}
        self.assertEqual(shared_ac_hash(story_a), shared_ac_hash(story_b))
        self.assertEqual(mcp_ac_hash(story_a), mcp_ac_hash(story_b))


if __name__ == "__main__":
    unittest.main()
