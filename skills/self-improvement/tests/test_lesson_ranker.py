"""Tests for the lesson relevance ranker."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lesson_ranker  # noqa: E402


LESSONS = [
    {"title": "Auth token fix", "content": "Fixed token expiry in authentication module",
     "anchored_paths": ["src/auth/token.py", "src/auth/session.py"]},
    {"title": "DB migration perf", "content": "Optimized database migration for users table",
     "anchored_paths": ["db/migrations/001.sql"]},
    {"title": "CSS cleanup", "content": "Removed unused CSS classes from dashboard",
     "anchored_paths": ["static/css/dashboard.css"]},
    {"title": "API rate limit", "content": "Added rate limiting to API endpoints",
     "anchored_paths": ["src/api/middleware.py"]},
]


class RankLessonsTests(unittest.TestCase):
    def test_max_lessons_limit(self):
        result = lesson_ranker.rank_lessons(LESSONS, ["src/auth/token.py"], "fix auth", max_lessons=2)
        self.assertLessEqual(len(result), 2)

    def test_file_overlap_scores_higher(self):
        result = lesson_ranker.rank_lessons(
            LESSONS, ["src/auth/token.py"], "fix something")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["title"], "Auth token fix")

    def test_text_relevance_alone(self):
        result = lesson_ranker.rank_lessons(LESSONS, [], "database migration optimization")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["title"], "DB migration perf")

    def test_zero_relevance_excluded(self):
        result = lesson_ranker.rank_lessons(
            LESSONS, ["unrelated/path.py"], "quantum physics experiment")
        self.assertEqual(len(result), 0)

    def test_empty_lessons(self):
        self.assertEqual(lesson_ranker.rank_lessons([], ["a.py"], "test"), [])

    def test_empty_changed_files(self):
        result = lesson_ranker.rank_lessons(LESSONS, [], "auth token")
        for r in result:
            self.assertIn("relevance_score", r)

    def test_empty_task_description(self):
        result = lesson_ranker.rank_lessons(LESSONS, ["src/auth/token.py"], "")
        self.assertGreater(len(result), 0)

    def test_combined_score_weights(self):
        result = lesson_ranker.rank_lessons(
            LESSONS, ["src/auth/token.py"], "authentication token expiry fix")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["title"], "Auth token fix")
        self.assertGreater(result[0]["relevance_score"], 0)

    def test_default_max_eight(self):
        many_lessons = [{"title": f"L{i}", "content": f"lesson about topic {i}",
                         "anchored_paths": [f"src/file{i}.py"]}
                        for i in range(20)]
        result = lesson_ranker.rank_lessons(
            many_lessons, [f"src/file{i}.py" for i in range(20)], "topic")
        self.assertLessEqual(len(result), 8)

    def test_original_fields_preserved(self):
        lessons = [{"title": "Test", "content": "test content", "anchored_paths": ["a.py"], "extra": 42}]
        result = lesson_ranker.rank_lessons(lessons, ["a.py"], "test")
        self.assertEqual(result[0]["extra"], 42)


if __name__ == "__main__":
    unittest.main()
