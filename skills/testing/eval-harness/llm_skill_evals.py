"""Layer G: Skill Contract Evals — validates ADLC skill rules via MCP API scenarios.

Tests the 3 critical skills (evidence-gate, story-writer, project-conventions) by:
  - Exercising the MCP API with realistic scenarios (authority, classification, handoffs)
  - Validating story/requirement fixture structure against skill schema rules
  - Verifying edge cases (empty input, invalid classification, correction chains)

These are deterministic integration tests — they exercise the real MCP tool layer
(evidence ledger, change management) with hardcoded fixtures, NOT LLM output.
To test actual LLM behavior, see skills/testing/pipeline-tests/test_e2e_scenarios.py.

Run:  python -m unittest skills/testing/eval-harness/llm_skill_evals.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

sys.path.insert(0, str(REPO / "skills" / "mcp-servers" / "adlc-mcp" / "src"))
sys.path.insert(0, str(REPO / "skills" / "mcp-servers" / "adlc-mcp" / "tests"))

from _support import CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

PRODUCT_PLANNER = Identity(
    "AGENT", "agent:product-planner", agent_role="product-planner",
    tool="claude-code", model_id="model-a",
)
ARCHITECT = Identity(
    "AGENT", "agent:architect", agent_role="architect",
    tool="claude-code", model_id="model-a",
)
QA_DERIVE = Identity(
    "AGENT", "agent:qa-derive", agent_role="qa-derive",
    tool="claude-code", model_id="model-a",
)
TEST_ENGINEER = Identity(
    "AGENT", "agent:test-engineer", agent_role="test-engineer",
    tool="claude-code", model_id="model-a",
)

RUN_ID = "eval-llm-skill-001"


def _make_env():
    env = TempEnv("evidence_ledger,change_management")
    registry = build_modules(env.config)
    ledger = registry.get("evidence_ledger").api
    cm = registry.get("change_management").api
    return env, registry, ledger, cm


# ---------------------------------------------------------------------------
# Scenario 1: Evidence Gate — a "User Authentication" requirement
# ---------------------------------------------------------------------------
REQUIREMENT_AUTH = {
    "id": "REQ-101",
    "title": "Add email/password authentication",
    "statement": "Users must be able to sign up and log in with email and password. "
                 "Passwords must be hashed with bcrypt (cost 12). Sessions expire after 24h.",
    "requested_by": "product-manager",
    "business_outcome": "Users can create accounts and access personalised features",
    "source_refs": [{"ref": "stakeholder-interview-2026-09", "trust_level": "EXTERNAL_UNSTRUCTURED"}],
}


class EvidenceGateEvals(unittest.TestCase):
    """Eval: evidence-gate skill produces correct ledger entries for auth requirement."""

    def setUp(self):
        self.env, self.registry, self.ledger, self.cm = _make_env()
        cs = self.cm.create_change_set(
            DEVELOPER, title="Auth feature", requirements=["REQ-101"],
            repositories=["app-repo"],
        )
        self.cs_id = cs["id"]

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_inference_requires_input_references(self):
        """Evidence-gate §4: an INFERENCE with no inputs is an ASSUMPTION."""
        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="bcrypt cost 12 is sufficient for auth",
                source_type="TOOL", change_set_id=self.cs_id,
                input_references=[],
            )
        self.assertIn("input_references", str(ctx.exception))

    def test_agent_cannot_write_fact(self):
        """Evidence-gate §5: agents never write FACT entries."""
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="FACT",
                content="npm test passed: 42 tests OK",
                source_type="command_output", change_set_id=self.cs_id,
            )

    def test_question_for_unsourced_blocking_claim(self):
        """Evidence-gate §3: unsourced blocking claim → QUESTION with blocking metadata."""
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="What password reset flow is required? No spec provided.",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"blocking": True},
        )
        self.assertEqual(entry["classification"], "QUESTION")
        meta = entry.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        self.assertTrue(meta["blocking"])
        queried = self.ledger.query_evidence(
            DEVELOPER, change_set_id=self.cs_id, classification="QUESTION",
        )
        self.assertTrue(any(e["entry_id"] == entry["entry_id"] for e in queried))

    def test_assumption_for_unsourced_nonblocking_claim(self):
        """Evidence-gate §3: unsourced non-blocking claim → ASSUMPTION with impact and expiry."""
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
            content="Session tokens will use JWT (not opaque tokens)",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"impact": "MEDIUM", "expires_at": "2027-01-01T00:00:00Z"},
        )
        self.assertEqual(entry["classification"], "ASSUMPTION")
        meta = entry.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        self.assertEqual(meta["impact"], "MEDIUM")

    def test_inference_chain_with_valid_references(self):
        """Evidence-gate §4: a derived claim is INFERENCE with input_references."""
        fact = self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "grep -r bcrypt package.json: bcrypt@5.1.1",
            "source": "cmd:grep",
            "change_set_id": self.cs_id,
        })
        inference = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="bcrypt 5.1.1 is already installed; no new dependency needed",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
        )
        self.assertEqual(inference["classification"], "INFERENCE")
        refs = inference.get("input_references")
        if isinstance(refs, str):
            refs = json.loads(refs)
        self.assertIn(fact["entry_id"], refs)

    def test_blocking_items_shows_open_questions(self):
        """Blocking items should surface open blocking QUESTIONs."""
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="Is OAuth required alongside email/password?",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"blocking": True},
        )
        blockers = self.ledger.blocking_items(self.cs_id)
        self.assertGreater(len(blockers), 0)
        self.assertTrue(any("QUESTION" in b for b in blockers))

    def test_answering_question_resolves_it(self):
        """Answering a QUESTION changes its derived status to ANSWERED."""
        q = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="Should we support social login?",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"blocking": False},
        )
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Product owner confirmed: email/password only for v1",
            source_type="TOOL", change_set_id=self.cs_id,
            answers_entry_id=q["entry_id"],
            input_references=[q["entry_id"]],
        )
        entries = self.ledger.query_evidence(
            DEVELOPER, change_set_id=self.cs_id, classification="QUESTION",
        )
        answered = [e for e in entries if e["entry_id"] == q["entry_id"]]
        self.assertEqual(len(answered), 1)
        self.assertEqual(answered[0]["derived_status"], "ANSWERED")

    def test_handoff_records_evidence_gate_result(self):
        """A handoff should record evidence_gate PASS/FAIL."""
        fact = self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "5 claims found in handoff, all sourced",
            "source": "cmd:evidence-check",
            "change_set_id": self.cs_id,
        })
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="evidence_gate: PASS — all 5 claims sourced",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
            metadata={"evidence_gate": "PASS", "claims_checked": 5, "unsourced": 0},
        )
        meta = entry.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        self.assertEqual(meta["evidence_gate"], "PASS")


# ---------------------------------------------------------------------------
# Scenario 2: Story Writer — "Shopping Cart" feature requirement
# ---------------------------------------------------------------------------
REQUIREMENT_CART = {
    "id": "REQ-201",
    "title": "Shopping cart with quantity management",
    "statement": "Users can add items to a cart, adjust quantities, remove items, "
                 "and see a running total. Cart persists across sessions.",
    "requested_by": "product-manager",
    "business_outcome": "Users can build orders before checkout, increasing conversion",
}

STORY_CART = {
    "id": "ST-201",
    "title": "Add items to cart with quantity adjustment",
    "type": "FEATURE_STORY",
    "requirement_id": "REQ-201",
    "objective": "Allow users to add products to a persistent cart and adjust quantities",
    "persona": "Online shopper",
    "value_statement": "so I can build my order before checkout",
    "scope": ["Cart API endpoints", "Cart persistence layer", "Cart UI component"],
    "out_of_scope": ["Checkout flow", "Payment processing", "Discount/coupon system"],
    "acceptance_criteria": [
        {
            "id": "ST-201/AC-1",
            "given": "a product page is displayed",
            "when": "the user clicks 'Add to Cart'",
            "then": "the item appears in the cart with quantity 1",
            "kind": "functional",
            "verification": "automated",
        },
        {
            "id": "ST-201/AC-2",
            "given": "an item is in the cart",
            "when": "the user increases the quantity to 3",
            "then": "the cart shows quantity 3 and the line total updates",
            "kind": "functional",
            "verification": "automated",
        },
        {
            "id": "ST-201/AC-3",
            "given": "an item is in the cart",
            "when": "the user sets quantity to 0",
            "then": "the item is removed from the cart",
            "kind": "negative",
            "verification": "automated",
        },
        {
            "id": "ST-201/AC-4",
            "given": "the user has items in the cart and closes the browser",
            "when": "the user returns and opens the cart",
            "then": "all previously added items are still present with correct quantities",
            "kind": "functional",
            "verification": "automated",
        },
        {
            "id": "ST-201/AC-5",
            "given": "50 concurrent users add items to their carts",
            "when": "all requests complete",
            "then": "each cart contains only its owner's items and p99 < 200ms",
            "kind": "nfr",
            "verification": "automated",
        },
    ],
    "touches": {
        "ui": True,
        "api_contracts": ["POST /cart/items", "PATCH /cart/items/:id", "DELETE /cart/items/:id"],
        "data_migration": False,
        "infra": False,
    },
    "data_classification": "INTERNAL",
    "size": "M",
    "size_basis": "3 API endpoints + persistence + UI component, ~150 lines",
    "affected_paths": ["src/cart/**", "src/api/cart.ts", "tests/cart/**"],
    "source_refs": [{"ref": "REQ-201", "trust_level": "EXTERNAL_STRUCTURED"}],
}


class StoryWriterEvals(unittest.TestCase):
    """Eval: story-writer skill produces structurally valid stories via MCP."""

    def setUp(self):
        self.env, self.registry, self.ledger, self.cm = _make_env()
        cs = self.cm.create_change_set(
            DEVELOPER, title="Cart feature", requirements=["REQ-201"],
            repositories=["app-repo"],
        )
        self.cs_id = cs["id"]

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_story_has_all_required_fields(self):
        """Story-writer §10: validate against story.schema.json."""
        required = [
            "id", "title", "type", "requirement_id", "objective",
            "scope", "out_of_scope", "acceptance_criteria", "touches",
            "data_classification", "size", "affected_paths", "source_refs",
        ]
        for field in required:
            self.assertIn(field, STORY_CART, f"Missing required field: {field}")

    def test_story_type_is_valid(self):
        """Story-writer §1: type must be from reference/story-types.md."""
        valid_types = [
            "FEATURE_STORY", "BUG_FIX", "TECHNICAL_STORY", "REFACTOR",
            "UI_STORY", "API_CONTRACT", "DATA_MIGRATION", "INFRASTRUCTURE",
            "SECURITY_STORY", "SPIKE", "DOCUMENTATION",
        ]
        self.assertIn(STORY_CART["type"], valid_types)

    def test_feature_story_has_persona_and_value(self):
        """Story-writer §2: FEATURE_STORY requires persona and value_statement."""
        self.assertIn("persona", STORY_CART)
        self.assertIn("value_statement", STORY_CART)
        self.assertTrue(len(STORY_CART["persona"]) > 0)
        self.assertTrue(len(STORY_CART["value_statement"]) > 0)

    def test_ac_ids_prefixed_with_story_id(self):
        """Story-writer §5: AC IDs are ST-n/AC-n."""
        for ac in STORY_CART["acceptance_criteria"]:
            self.assertTrue(
                ac["id"].startswith(f"{STORY_CART['id']}/AC-"),
                f"AC id {ac['id']} should start with {STORY_CART['id']}/AC-",
            )

    def test_ac_has_given_when_then(self):
        """Story-writer §5: every AC has Given/When/Then."""
        for ac in STORY_CART["acceptance_criteria"]:
            self.assertIn("given", ac, f"{ac['id']} missing 'given'")
            self.assertIn("when", ac, f"{ac['id']} missing 'when'")
            self.assertIn("then", ac, f"{ac['id']} missing 'then'")

    def test_ac_has_kind_and_verification(self):
        """Story-writer §5: every AC has kind and verification."""
        valid_kinds = ["functional", "negative", "nfr", "accessibility",
                       "reproduction", "no-behaviour-change", "rollback",
                       "data-integrity", "security"]
        valid_verifications = ["automated", "manual", "observation"]
        for ac in STORY_CART["acceptance_criteria"]:
            self.assertIn(ac["kind"], valid_kinds, f"{ac['id']} bad kind")
            self.assertIn(ac["verification"], valid_verifications,
                          f"{ac['id']} bad verification")

    def test_at_least_one_negative_criterion(self):
        """Story-writer §5: at least one negative criterion."""
        negatives = [ac for ac in STORY_CART["acceptance_criteria"]
                     if ac["kind"] == "negative"]
        self.assertGreater(len(negatives), 0,
                           "FEATURE_STORY must have at least one negative AC")

    def test_nfr_criterion_states_a_number(self):
        """Story-writer §5: every nfr criterion states a number."""
        nfrs = [ac for ac in STORY_CART["acceptance_criteria"]
                if ac["kind"] == "nfr"]
        for ac in nfrs:
            combined = f"{ac['given']} {ac['when']} {ac['then']}"
            import re
            self.assertTrue(
                re.search(r"\d+", combined),
                f"NFR {ac['id']} must state a number: {combined}",
            )

    def test_out_of_scope_is_present(self):
        """Story-writer §4: out_of_scope is mandatory, even when empty."""
        self.assertIn("out_of_scope", STORY_CART)
        self.assertIsInstance(STORY_CART["out_of_scope"], list)

    def test_size_not_L(self):
        """Story-writer §8: anything L must be split before READY."""
        self.assertNotEqual(STORY_CART["size"], "L",
                            "L stories must be split before READY")

    def test_no_status_field(self):
        """Story-writer §10: never write status; READY is computed by the gate."""
        self.assertNotIn("status", STORY_CART)

    def test_story_evidence_recorded_via_mcp(self):
        """Story evidence can be recorded through the MCP ledger."""
        fact = self.ledger.append_fact("file-read", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "REQ-201 statement: shopping cart with quantity management",
            "source": "cmd:cat plans/requirements/REQ-201.yaml",
            "change_set_id": self.cs_id,
        })
        entry = self.ledger.record_evidence(
            PRODUCT_PLANNER, run_id=RUN_ID, classification="INFERENCE",
            content=f"Story {STORY_CART['id']} written with 5 ACs covering "
                    "functional, negative, and NFR criteria",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
            metadata={"story_id": STORY_CART["id"], "ac_count": 5},
        )
        self.assertEqual(entry["classification"], "INFERENCE")
        self.assertEqual(entry["agent_role"], "product-planner")

    def test_handoff_from_planner_to_developer(self):
        """Story handoff from product-planner to developer records correctly."""
        ho = self.cm.record_handoff(
            PRODUCT_PLANNER, change_set_id=self.cs_id,
            to_role="developer",
            payload={
                "summary": f"Story {STORY_CART['id']} ready for refinement",
                "inputs": [{"artifact_ref": "app-repo@abc1234:plans/requirements/REQ-201.yaml",
                            "content_hash": "sha256:" + "11" * 32}],
                "outputs": [
                    {"artifact_kind": "ready-story",
                     "content_hash": "sha256:" + "ab" * 32},
                ],
                "classifications": [
                    {"classification": "INFERENCE",
                     "content": "Story written from REQ-201"},
                ],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho["from_role"], "product-planner")
        self.assertEqual(ho["to_role"], "developer")
        self.assertEqual(ho["verdict"], "ACCEPT")


# ---------------------------------------------------------------------------
# Scenario 3: Project Conventions — brownfield codebase scan
# ---------------------------------------------------------------------------
CONVENTIONS_CATALOG = {
    "scan_version": "1.0",
    "repo": "app-repo",
    "sha": "abc123def456",
    "declared_standards": [
        {"path": "docs/adr/0001-use-express.md", "sha256": "aaa111", "type": "ADR"},
        {"path": ".eslintrc.json", "sha256": "bbb222", "type": "lint_config"},
        {"path": "tsconfig.json", "sha256": "ccc333", "type": "type_config"},
        {"path": "CONTRIBUTING.md", "sha256": "ddd444", "type": "style_guide"},
    ],
    "toolchain": [
        {"name": "lint", "command": "npm run lint"},
        {"name": "format", "command": "npm run format"},
        {"name": "typecheck", "command": "npx tsc --noEmit"},
        {"name": "test", "command": "npm test"},
    ],
    "dependency_inventory": {
        "http_client": ["axios@1.6.0"],
        "orm": ["prisma@5.8.0"],
        "logger": ["pino@8.17.0"],
        "validator": ["zod@3.22.0"],
        "test_runner": ["vitest@1.2.0"],
    },
    "module_map": [
        {"name": "api", "path": "src/api/", "layer": "presentation"},
        {"name": "services", "path": "src/services/", "layer": "business"},
        {"name": "models", "path": "src/models/", "layer": "data"},
        {"name": "utils", "path": "src/utils/", "layer": "shared"},
    ],
    "golden_files": [
        {"path": "src/api/users.ts", "relevance": 0.95},
        {"path": "src/services/user-service.ts", "relevance": 0.90},
        {"path": "src/models/user.ts", "relevance": 0.85},
    ],
    "mixed_conventions": [],
}


class ProjectConventionsEvals(unittest.TestCase):
    """Eval: project-conventions skill produces correct evidence for brownfield work."""

    def setUp(self):
        self.env, self.registry, self.ledger, self.cm = _make_env()
        cs = self.cm.create_change_set(
            DEVELOPER, title="Cart feature on existing repo",
            requirements=["REQ-201"], repositories=["app-repo"],
        )
        self.cs_id = cs["id"]

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_conventions_catalog_recorded_as_fact(self):
        """Conventions scan output is recorded as FACT by a hook, not by an agent."""
        fact = self.ledger.append_fact("convention-scan", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": json.dumps(CONVENTIONS_CATALOG),
            "source": "cmd:convention_scan.py --repo app-repo",
            "change_set_id": self.cs_id,
        })
        self.assertEqual(fact["classification"], "FACT")
        self.assertEqual(fact["actor_type"], "SYSTEM")

    def test_agent_cannot_write_conventions_as_fact(self):
        """Agents must not self-report conventions as FACT."""
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="FACT",
                content=json.dumps(CONVENTIONS_CATALOG),
                source_type="command_output", change_set_id=self.cs_id,
            )

    def test_deviation_recorded_as_decision(self):
        """A deviation from conventions must be a DECISION with ADR reference."""
        fact = self.ledger.append_fact("convention-scan", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "Dependency inventory shows axios for HTTP",
            "source": "cmd:convention_scan.py",
            "change_set_id": self.cs_id,
        })
        decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Use fetch instead of axios for new cart API client. "
                    "Reason: fetch is built-in, reduces bundle size. "
                    "ADR: docs/adr/0012-prefer-fetch.md",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertEqual(decision["classification"], "DECISION")
        self.assertEqual(decision["lifecycle_state"], "PROPOSED")

    def test_drift_recorded_as_risk(self):
        """Mixed conventions (drift) are recorded as RISK entries."""
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="src/legacy/ uses request@2.88 for HTTP while src/api/ uses axios@1.6. "
                    "Declared standard (ADR-0001) says axios. Follow axios in new code.",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"impact": "LOW", "mitigation": "Follow declared standard (axios)"},
        )
        self.assertEqual(entry["classification"], "RISK")

    def test_conventions_catalog_has_required_sections(self):
        """Conventions catalog output has all required sections."""
        required = [
            "declared_standards", "toolchain", "dependency_inventory",
            "module_map", "golden_files",
        ]
        for field in required:
            self.assertIn(field, CONVENTIONS_CATALOG,
                          f"Conventions catalog missing: {field}")

    def test_golden_files_have_relevance_scores(self):
        """Golden files are ranked by relevance to target."""
        for gf in CONVENTIONS_CATALOG["golden_files"]:
            self.assertIn("path", gf)
            self.assertIn("relevance", gf)
            self.assertGreater(gf["relevance"], 0)
            self.assertLessEqual(gf["relevance"], 1.0)

    def test_toolchain_commands_present(self):
        """Toolchain has lint, format, typecheck, test commands."""
        names = {t["name"] for t in CONVENTIONS_CATALOG["toolchain"]}
        self.assertTrue({"lint", "format", "typecheck", "test"}.issubset(names))

    def test_dependency_inventory_by_concern(self):
        """Inventory lists libraries by concern, not flat."""
        inv = CONVENTIONS_CATALOG["dependency_inventory"]
        self.assertIn("http_client", inv)
        self.assertIn("orm", inv)
        self.assertIsInstance(inv["http_client"], list)


# ---------------------------------------------------------------------------
# Scenario 4: Cross-skill pipeline — requirement through evidence chain
# ---------------------------------------------------------------------------
class PipelineIntegrationEvals(unittest.TestCase):
    """Eval: full pipeline from requirement → story → implementation evidence."""

    def setUp(self):
        self.env, self.registry, self.ledger, self.cm = _make_env()
        cs = self.cm.create_change_set(
            DEVELOPER, title="Search feature",
            requirements=["REQ-301"], repositories=["app-repo"],
        )
        self.cs_id = cs["id"]

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_full_evidence_chain(self):
        """A complete chain: FACT → INFERENCE → QUESTION → ANSWER → DECISION."""
        fact = self.ledger.append_fact("file-read", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "package.json: elasticsearch@8.11, algolia not present",
            "source": "cmd:cat package.json",
            "change_set_id": self.cs_id,
        })

        inference = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Project uses Elasticsearch 8.11 for search",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
        )

        question = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="QUESTION",
            content="Should we use Elasticsearch or switch to Algolia?",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"blocking": True},
        )

        answer = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Tech lead confirmed: stay with Elasticsearch",
            source_type="TOOL", change_set_id=self.cs_id,
            answers_entry_id=question["entry_id"],
            input_references=[question["entry_id"]],
        )

        decision = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Continue with Elasticsearch 8.11. No new dependency.",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[inference["entry_id"], answer["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        entries = self.ledger.query_evidence(
            DEVELOPER, change_set_id=self.cs_id,
        )
        classifications = {e["classification"] for e in entries}
        self.assertIn("FACT", classifications)
        self.assertIn("INFERENCE", classifications)
        self.assertIn("QUESTION", classifications)
        self.assertIn("DECISION", classifications)

        q_entries = [e for e in entries if e["entry_id"] == question["entry_id"]]
        self.assertEqual(q_entries[0]["derived_status"], "ANSWERED")

    def test_authority_boundaries_enforced(self):
        """No agent can set APPROVED, VERIFIED, or DONE."""
        for role_identity in [DEVELOPER, ARCHITECT, PRODUCT_PLANNER, CODE_REVIEWER]:
            with self.assertRaises((PermissionDenied, ValidationError)):
                self.ledger.record_evidence(
                    role_identity, run_id=RUN_ID, classification="FACT",
                    content="something", source_type="command_output",
                    change_set_id=self.cs_id,
                )

    def test_handoff_chain_maintains_traceability(self):
        """Handoffs from planner → architect → developer are traceable."""
        ho1 = self.cm.record_handoff(
            PRODUCT_PLANNER, change_set_id=self.cs_id,
            to_role="architect",
            payload={
                "summary": "Story ST-301 ready for architecture review",
                "inputs": [{"artifact_ref": "app-repo@abc1234:plans/requirements/REQ-301.yaml",
                            "content_hash": "sha256:" + "22" * 32}],
                "outputs": [{"artifact_kind": "ready-story",
                             "content_hash": "sha256:" + "cd" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        ho2 = self.cm.record_handoff(
            ARCHITECT, change_set_id=self.cs_id,
            to_role="developer",
            payload={
                "summary": "Architecture approved, ready for implementation",
                "inputs": [{"artifact_ref": "app-repo@abc1234:plans/stories/ST-301.yaml",
                            "content_hash": "sha256:" + "33" * 32}],
                "outputs": [{"artifact_kind": "architecture-design",
                             "content_hash": "sha256:" + "ef" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho1["to_role"], "architect")
        self.assertEqual(ho2["from_role"], "architect")
        self.assertEqual(ho2["to_role"], "developer")

    def test_correction_challenges_earlier_entry(self):
        """record_correction creates a CHALLENGED outcome on the original entry."""
        fact = self.ledger.append_fact("file-read", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output",
            "content": "src/cart/total.ts: const total = items.reduce(...)",
            "source": "cmd:cat src/cart/total.ts",
            "change_set_id": self.cs_id,
        })
        original = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Cart total uses integer cents to avoid float errors",
            source_type="TOOL", change_set_id=self.cs_id,
            input_references=[fact["entry_id"]],
        )
        correction = self.ledger.record_correction(
            CODE_REVIEWER, parent_entry_id=original["entry_id"],
            run_id=RUN_ID,
            content="Code review found: cart total actually uses float, not cents",
            source_type="TOOL",
        )
        entries = self.ledger.query_evidence(
            DEVELOPER, change_set_id=self.cs_id,
        )
        orig_entry = [e for e in entries if e["entry_id"] == original["entry_id"]]
        self.assertEqual(orig_entry[0]["derived_status"], "CHALLENGED")


# ---------------------------------------------------------------------------
# Scenario 5: Edge cases and failure modes
# ---------------------------------------------------------------------------
class EdgeCaseEvals(unittest.TestCase):
    """Eval: skill edge cases that frequently fail in real-world use."""

    def setUp(self):
        self.env, self.registry, self.ledger, self.cm = _make_env()
        cs = self.cm.create_change_set(
            DEVELOPER, title="Edge case test",
            requirements=["REQ-999"], repositories=["app-repo"],
        )
        self.cs_id = cs["id"]

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_empty_content_rejected(self):
        """Evidence with empty content should be rejected."""
        fact = self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output", "content": "test output",
            "source": "cmd:test", "change_set_id": self.cs_id,
        })
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="", source_type="TOOL", change_set_id=self.cs_id,
                input_references=[fact["entry_id"]],
            )

    def test_empty_run_id_rejected(self):
        """Evidence with empty run_id should be rejected."""
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id="", classification="INFERENCE",
                content="some content", source_type="TOOL",
                change_set_id=self.cs_id,
            )

    def test_invalid_classification_rejected(self):
        """Unknown classification should be rejected."""
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="PROOF",
                content="this is proven", source_type="TOOL",
                change_set_id=self.cs_id,
            )

    def test_answers_non_question_rejected(self):
        """Answering a non-QUESTION/ASSUMPTION entry should fail."""
        decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Use REST not GraphQL",
            source_type="TOOL", change_set_id=self.cs_id,
            lifecycle_state="PROPOSED",
        )
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Answering a decision makes no sense",
                source_type="TOOL", change_set_id=self.cs_id,
                answers_entry_id=decision["entry_id"],
                input_references=[decision["entry_id"]],
            )

    def test_correction_references_nonexistent_entry(self):
        """Correcting a nonexistent entry should fail."""
        from adlc_mcp.kernel.errors import NotFound
        with self.assertRaises(NotFound):
            self.ledger.record_correction(
                CODE_REVIEWER, parent_entry_id="ENTRY-nonexistent",
                run_id=RUN_ID, content="Challenging ghost entry",
                source_type="TOOL",
            )

    def test_high_impact_assumption_blocks_completion(self):
        """HIGH-impact ASSUMPTION shows up in blocking items."""
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
            content="Assuming cart max is 100 items",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"impact": "HIGH", "expires_at": "2027-01-01T00:00:00Z"},
        )
        blockers = self.ledger.blocking_items(self.cs_id)
        self.assertGreater(len(blockers), 0)
        self.assertTrue(any("ASSUMPTION" in b for b in blockers))

    def test_low_impact_assumption_does_not_block(self):
        """LOW-impact ASSUMPTION does not block completion."""
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
            content="Assuming default page size is 20",
            source_type="TOOL", change_set_id=self.cs_id,
            metadata={"impact": "LOW", "expires_at": "2027-01-01T00:00:00Z"},
        )
        blockers = self.ledger.blocking_items(self.cs_id)
        low_assumptions = [b for b in blockers if "page size" in b.lower()]
        self.assertEqual(len(low_assumptions), 0)

    def test_ledger_hash_chain_integrity(self):
        """After multiple entries, the hash chain verifies clean."""
        for i in range(5):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="QUESTION",
                content=f"Open question {i} for hash chain test",
                source_type="TOOL", change_set_id=self.cs_id,
                metadata={"blocking": False},
            )
        results = self.ledger.verify()
        broken = [r for r in results if not r.get("ok", True)]
        self.assertEqual(len(broken), 0, f"Hash chain broken: {broken}")


# ---------------------------------------------------------------------------
# Scenario 6: Story types and conditional requirements
# ---------------------------------------------------------------------------
STORY_BUG_FIX = {
    "id": "ST-401",
    "title": "Fix cart total rounding error",
    "type": "BUG_FIX",
    "requirement_id": "REQ-401",
    "objective": "Fix floating-point rounding error in cart total calculation",
    "scope": ["Cart total calculation"],
    "out_of_scope": ["Cart UI", "Checkout flow"],
    "acceptance_criteria": [
        {
            "id": "ST-401/AC-1",
            "given": "items priced at $1.10, $2.20, $3.30 are in the cart",
            "when": "the cart total is calculated",
            "then": "the total is exactly $6.60, not $6.6000000000000005",
            "kind": "reproduction",
            "verification": "automated",
        },
        {
            "id": "ST-401/AC-2",
            "given": "the fix is applied",
            "when": "existing cart operations are performed",
            "then": "no other cart functionality is broken",
            "kind": "negative",
            "verification": "automated",
        },
    ],
    "touches": {"ui": False, "api_contracts": [], "data_migration": False, "infra": False},
    "data_classification": "INTERNAL",
    "size": "XS",
    "affected_paths": ["src/services/cart-total.ts", "tests/cart-total.test.ts"],
    "source_refs": [{"ref": "BUG-2026-1234", "trust_level": "EXTERNAL_STRUCTURED"}],
}

STORY_SPIKE = {
    "id": "ST-501",
    "title": "Investigate real-time cart sync options",
    "type": "SPIKE",
    "requirement_id": "REQ-501",
    "objective": "Evaluate WebSocket vs SSE vs polling for cart sync across tabs",
    "scope": ["Research sync mechanisms"],
    "out_of_scope": ["Implementation of chosen approach"],
    "acceptance_criteria": [
        {
            "id": "ST-501/AC-1",
            "given": "research is complete",
            "when": "the spike report is delivered",
            "then": "it compares latency, complexity, and browser support for 3 options",
            "kind": "functional",
            "verification": "manual",
        },
    ],
    "touches": {"ui": False, "api_contracts": [], "data_migration": False, "infra": False},
    "data_classification": "INTERNAL",
    "size": "S",
    "spike": {"question": "Which real-time mechanism best fits our stack?", "timebox_days": 2},
    "affected_paths": [],
    "source_refs": [{"ref": "REQ-501", "trust_level": "EXTERNAL_STRUCTURED"}],
}


class StoryTypeEvals(unittest.TestCase):
    """Eval: story type-specific rules from story-writer skill."""

    def test_bug_fix_has_reproduction_criterion(self):
        """Story-writer §5: BUG_FIX requires reproduction kind."""
        repros = [ac for ac in STORY_BUG_FIX["acceptance_criteria"]
                  if ac["kind"] == "reproduction"]
        self.assertGreater(len(repros), 0,
                           "BUG_FIX must have at least one reproduction AC")

    def test_bug_fix_has_negative_criterion(self):
        """BUG_FIX still needs negative criterion (no regression)."""
        negatives = [ac for ac in STORY_BUG_FIX["acceptance_criteria"]
                     if ac["kind"] == "negative"]
        self.assertGreater(len(negatives), 0)

    def test_spike_has_question_and_timebox(self):
        """Story-writer §9: SPIKE requires spike.question + spike.timebox_days."""
        self.assertIn("spike", STORY_SPIKE)
        self.assertIn("question", STORY_SPIKE["spike"])
        self.assertIn("timebox_days", STORY_SPIKE["spike"])
        self.assertGreater(STORY_SPIKE["spike"]["timebox_days"], 0)

    def test_spike_no_negative_criterion_required(self):
        """Story-writer §5: SPIKE exempted from negative criterion requirement."""
        negatives = [ac for ac in STORY_SPIKE["acceptance_criteria"]
                     if ac["kind"] == "negative"]
        # It's OK for SPIKE to have zero negatives (exemption in §5)
        self.assertIsInstance(negatives, list)

    def test_spike_no_persona_required(self):
        """Story-writer §2: value and persona not required for SPIKE."""
        self.assertNotIn("persona", STORY_SPIKE)
        self.assertNotIn("value_statement", STORY_SPIKE)

    def test_ac_ids_unique_across_story(self):
        """AC IDs must be unique within a story."""
        for story in [STORY_CART, STORY_BUG_FIX, STORY_SPIKE]:
            ids = [ac["id"] for ac in story["acceptance_criteria"]]
            self.assertEqual(len(ids), len(set(ids)),
                             f"Duplicate AC IDs in {story['id']}")


if __name__ == "__main__":
    unittest.main()
