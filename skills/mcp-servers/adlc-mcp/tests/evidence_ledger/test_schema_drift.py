"""C1: Verify ledger-entry.schema.json stays in sync with store.py's SQLite columns.

The migration SQL defines the evidence table's columns; the JSON schema's
``properties`` must list exactly the same set. This test catches drift.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SCHEMA_PATH = REPO / "skills" / "core" / "schemas" / "ledger-entry.schema.json"
MIGRATIONS_DIR = (
    REPO / "skills" / "mcp-servers" / "adlc-mcp" / "src" / "adlc_mcp"
    / "modules" / "evidence_ledger" / "migrations"
)

_COL_RE = re.compile(r"^\s+(\w+)\s+(?:INTEGER|TEXT|REAL)", re.MULTILINE)


def _extract_columns(table_name: str) -> set[str]:
    """Parse column names from CREATE TABLE + ALTER TABLE across all migration files."""
    cols: set[str] = set()
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text(encoding="utf-8")
        for block in re.finditer(
            rf"CREATE\s+TABLE\s+{table_name}\s*\((.*?)\);",
            sql,
            re.DOTALL | re.IGNORECASE,
        ):
            for m in _COL_RE.finditer(block.group(1)):
                cols.add(m.group(1))
        for m in re.finditer(
            rf"ALTER\s+TABLE\s+{table_name}\s+ADD\s+COLUMN\s+(\w+)",
            sql,
            re.IGNORECASE,
        ):
            cols.add(m.group(1))
    return cols


class LedgerSchemaDriftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.sql_cols = _extract_columns("evidence")

    def test_schema_properties_match_sql_columns(self):
        schema_props = set(self.schema["properties"].keys())
        self.assertEqual(
            schema_props,
            self.sql_cols,
            f"Schema vs SQL drift.\n"
            f"  In schema only: {schema_props - self.sql_cols}\n"
            f"  In SQL only:    {self.sql_cols - schema_props}",
        )

    def test_required_fields_are_not_null_in_sql(self):
        """Every 'required' field in the JSON schema should be NOT NULL in the SQL."""
        sql_text = ""
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            sql_text += f.read_text(encoding="utf-8")

        for field in self.schema.get("required", []):
            not_null = re.search(
                rf"^\s+{field}\s+\w+\s+NOT\s+NULL",
                sql_text,
                re.MULTILINE | re.IGNORECASE,
            )
            pk = re.search(
                rf"^\s+{field}\s+INTEGER\s+PRIMARY\s+KEY",
                sql_text,
                re.MULTILINE | re.IGNORECASE,
            )
            self.assertTrue(
                not_null or pk,
                f"JSON schema requires '{field}' but SQL column is not NOT NULL or PRIMARY KEY",
            )

    def test_sql_columns_not_empty(self):
        self.assertTrue(len(self.sql_cols) > 0, "No columns parsed from migrations")


if __name__ == "__main__":
    unittest.main()
