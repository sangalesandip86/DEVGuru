"""AAT-ASI08: Resource Abuse Tests (OWASP ASI08 — Denial of Wallet / DoS).

Exercises that oversized inputs, rapid writes, and edge-case payloads don't
crash the platform or corrupt data integrity.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _support import CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv  # noqa: E402

from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import AdlcError, ValidationError  # noqa: E402
from adlc_mcp.modules.evidence_ledger.api import open_ledger  # noqa: E402


class ASI08OversizedPayloads(unittest.TestCase):
    """Oversized inputs don't crash the system or corrupt the hash chain."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger")
        self.db = self.env.config.db_path("evidence_ledger")
        self.ledger = open_ledger(self.db, "abc1234")

    def tearDown(self):
        self.ledger._store.conn.close()
        self.env.close()

    def test_001_large_content(self):
        """Evidence with 100KB content field is handled without crash."""
        large_content = "x" * 100_000
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-large-001",
            classification="PROPOSAL",
            content=large_content,
            source_type="agent_analysis",
            source="test",
        )
        self.assertIsNotNone(result["entry_id"])
        chain = self.ledger.verify()
        for check in chain:
            self.assertTrue(check["ok"], f"chain broken after large content: {check}")

    def test_002_deeply_nested_metadata(self):
        """Deeply nested metadata (50 levels) doesn't cause stack overflow."""
        nested: dict = {"value": "leaf"}
        for _ in range(50):
            nested = {"child": nested}
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-nested-001",
            classification="PROPOSAL",
            content="nested metadata test",
            source_type="agent_analysis",
            source="test",
            metadata=nested,
        )
        self.assertIsNotNone(result["entry_id"])

    def test_003_empty_content_rejected(self):
        """Empty or whitespace-only content is rejected."""
        for empty in ("", "   ", "\n\t"):
            with self.assertRaises(ValidationError, msg=f"should reject {empty!r}"):
                self.ledger.record_evidence(
                    DEVELOPER,
                    run_id=f"R-empty-{hash(empty)}",
                    classification="PROPOSAL",
                    content=empty,
                    source_type="agent_analysis",
                    source="test",
                )

    def test_004_very_long_run_id(self):
        """A very long run_id is handled (stored or rejected, not crashed)."""
        long_id = "R-" + "a" * 10_000
        try:
            result = self.ledger.record_evidence(
                DEVELOPER,
                run_id=long_id,
                classification="PROPOSAL",
                content="long run_id test",
                source_type="agent_analysis",
                source="test",
            )
            self.assertEqual(result["run_id"], long_id)
        except (ValidationError, AdlcError):
            pass  # rejection is also acceptable


class ASI08LedgerIntegrity(unittest.TestCase):
    """Rapid and concurrent-style writes maintain hash chain integrity."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger")
        self.db = self.env.config.db_path("evidence_ledger")
        self.ledger = open_ledger(self.db, "abc1234")

    def tearDown(self):
        self.ledger._store.conn.close()
        self.env.close()

    def test_005_rapid_sequential_writes_preserve_chain(self):
        """100 rapid sequential evidence entries maintain hash chain integrity."""
        for i in range(100):
            self.ledger.record_evidence(
                DEVELOPER,
                run_id=f"R-rapid-{i:04d}",
                classification="PROPOSAL",
                content=f"entry {i}",
                source_type="agent_analysis",
                source="test",
            )
        chain = self.ledger.verify()
        for check in chain:
            self.assertTrue(check["ok"], f"chain broken after rapid writes: {check}")
        evidence_check = next(c for c in chain if c["table"] == "evidence")
        self.assertEqual(evidence_check["checked"], 100)

    def test_006_duplicate_run_ids_coexist(self):
        """Multiple entries with the same run_id don't collide or corrupt data."""
        entry_ids = []
        for i in range(5):
            result = self.ledger.record_evidence(
                DEVELOPER,
                run_id="R-shared-run",
                classification="PROPOSAL",
                content=f"entry {i} under shared run",
                source_type="agent_analysis",
                source="test",
            )
            entry_ids.append(result["entry_id"])
        self.assertEqual(len(set(entry_ids)), 5)
        chain = self.ledger.verify()
        for check in chain:
            self.assertTrue(check["ok"], f"chain broken after duplicate run_ids: {check}")
        evidence_check = next(c for c in chain if c["table"] == "evidence")
        self.assertEqual(evidence_check["checked"], 5)

    def test_007_interleaved_roles_preserve_chain(self):
        """Entries from different roles interleaved don't break the hash chain."""
        roles = [DEVELOPER, CODE_REVIEWER, SECURITY]
        for i in range(30):
            role = roles[i % 3]
            self.ledger.record_evidence(
                role,
                run_id=f"R-interleave-{i:03d}",
                classification="PROPOSAL",
                content=f"from {role.agent_role}",
                source_type="agent_analysis",
                source="test",
            )
        chain = self.ledger.verify()
        for check in chain:
            self.assertTrue(check["ok"], f"chain broken after interleaved writes: {check}")


class ASI08HandoffPayloadAbuse(unittest.TestCase):
    """Handoff payloads with unusual sizes or structures are handled."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_008_many_handoff_claims(self):
        """Handoff with 100 claims is handled without crash."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        claims = [{"classification": "PROPOSAL", "text": f"claim {i}", "source": f"src-{i}"}
                  for i in range(100)]
        h = self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                    payload={"claims": claims})
        self.assertEqual(h["from_role"], "developer")

    def test_009_empty_payload_accepted(self):
        """An empty handoff payload is valid (no claims, no inputs)."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        h = self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                    payload={})
        self.assertEqual(h["from_role"], "developer")

    def test_010_null_fields_in_payload(self):
        """Payload with explicit None/null values doesn't crash."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        h = self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                    payload={"claims": None, "inputs": None})
        self.assertEqual(h["from_role"], "developer")


if __name__ == "__main__":
    unittest.main()
