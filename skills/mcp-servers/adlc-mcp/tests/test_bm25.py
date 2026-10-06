"""Tests for the BM25 search module."""
from __future__ import annotations

import unittest

from adlc_mcp.modules.evidence_ledger.bm25 import bm25_search, tokenize


class TokenizeTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(tokenize("Hello World"), ["hello", "world"])

    def test_unicode(self):
        tokens = tokenize("café naïve")
        self.assertTrue(len(tokens) >= 2)

    def test_empty(self):
        self.assertEqual(tokenize(""), [])

    def test_punctuation(self):
        self.assertEqual(tokenize("foo.bar-baz"), ["foo", "bar", "baz"])


class BM25Tests(unittest.TestCase):
    def test_empty_corpus(self):
        self.assertEqual(bm25_search("test", []), [])

    def test_empty_query(self):
        self.assertEqual(bm25_search("", [{"content": "hello"}]), [])

    def test_single_match(self):
        corpus = [{"content": "fix authentication bug in login", "id": 1}]
        results = bm25_search("authentication login", corpus)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 1)
        self.assertIn("relevance_score", results[0])
        self.assertGreater(results[0]["relevance_score"], 0)

    def test_irrelevant_query(self):
        corpus = [{"content": "fix authentication bug", "id": 1}]
        results = bm25_search("quantum physics experiment", corpus)
        self.assertEqual(results, [])

    def test_ranking_exact_over_partial(self):
        corpus = [
            {"content": "database migration script for postgres", "id": 1},
            {"content": "postgres connection pool optimization database", "id": 2},
            {"content": "update readme documentation", "id": 3},
        ]
        results = bm25_search("postgres database migration", corpus)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["id"], 1)

    def test_top_n_limits(self):
        corpus = [{"content": f"item {i} with keyword match", "id": i} for i in range(20)]
        results = bm25_search("keyword match", corpus, top_n=5)
        self.assertLessEqual(len(results), 5)

    def test_k1_b_params(self):
        corpus = [
            {"content": "test test test repeated keyword", "id": 1},
            {"content": "test single mention", "id": 2},
        ]
        r1 = bm25_search("test", corpus, k1=0.0)
        r2 = bm25_search("test", corpus, k1=3.0)
        self.assertEqual(len(r1), 2)
        self.assertEqual(len(r2), 2)

    def test_custom_content_key(self):
        corpus = [{"description": "auth fix for login", "id": 1}]
        results = bm25_search("auth login", corpus, content_key="description")
        self.assertEqual(len(results), 1)

    def test_missing_content_key(self):
        corpus = [{"id": 1}]
        results = bm25_search("test", corpus)
        self.assertEqual(results, [])

    def test_original_item_preserved(self):
        corpus = [{"content": "fix bug", "id": 42, "extra": "data"}]
        results = bm25_search("fix bug", corpus)
        self.assertEqual(results[0]["extra"], "data")
        self.assertEqual(results[0]["id"], 42)


if __name__ == "__main__":
    unittest.main()
