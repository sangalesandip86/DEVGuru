#!/usr/bin/env python3
"""Rank lessons by relevance to current task context.

Uses BM25-style scoring over file-path overlap and text relevance.
Stdlib only. Reads JSON from stdin, outputs ranked lessons as JSON.

Usage:
    echo '{"lessons":[...],"changed_files":[...],"task_description":"..."}' | python lesson_ranker.py
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import PurePosixPath


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], avg_dl: float,
                n: int, df: dict[str, int], k1: float = 1.5, b: float = 0.75) -> float:
    tf = Counter(doc_tokens)
    dl = len(doc_tokens)
    score = 0.0
    for qt in query_tokens:
        if qt not in df:
            continue
        idf = math.log((n - df[qt] + 0.5) / (df[qt] + 0.5) + 1.0)
        term_tf = tf.get(qt, 0)
        score += idf * term_tf * (k1 + 1) / (term_tf + k1 * (1 - b + b * dl / avg_dl))
    return score


def _file_overlap(lesson_paths: list[str], changed_files: list[str]) -> float:
    if not lesson_paths or not changed_files:
        return 0.0
    lesson_set = {PurePosixPath(p.replace("\\", "/")).name for p in lesson_paths}
    changed_set = {PurePosixPath(p.replace("\\", "/")).name for p in changed_files}
    overlap = len(lesson_set & changed_set)
    union = len(lesson_set | changed_set)
    return overlap / union if union else 0.0


def rank_lessons(lessons: list[dict], changed_files: list[str],
                 task_description: str, max_lessons: int = 8) -> list[dict]:
    """Return up to max_lessons ranked by combined file-overlap + text relevance."""
    if not lessons:
        return []

    query_tokens = _tokenize(task_description)
    doc_tokens_list = [_tokenize(str(l.get("content", "") + " " + l.get("title", ""))) for l in lessons]
    n = len(lessons)
    avg_dl = sum(len(d) for d in doc_tokens_list) / n if n else 1.0

    df: dict[str, int] = {}
    for tokens in doc_tokens_list:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    scored: list[tuple[float, int]] = []
    for idx, lesson in enumerate(lessons):
        file_score = _file_overlap(lesson.get("anchored_paths", []), changed_files)
        text_score = 0.0
        if query_tokens:
            raw = _bm25_score(query_tokens, doc_tokens_list[idx], avg_dl, n, df)
            text_score = min(raw / 10.0, 1.0) if raw > 0 else 0.0

        combined = 0.6 * file_score + 0.4 * text_score
        if combined > 0:
            scored.append((combined, idx))

    scored.sort(key=lambda x: -x[0])
    result = []
    for score, idx in scored[:max_lessons]:
        item = {**lessons[idx], "relevance_score": round(score, 4)}
        result.append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank lessons by relevance")
    parser.add_argument("--check", action="store_true", help="Built-in self-test")
    args = parser.parse_args()

    if args.check:
        lessons = [
            {"title": "Auth bugfix", "content": "Fixed auth token expiry", "anchored_paths": ["src/auth/token.py"]},
            {"title": "DB migration", "content": "Added index to users table", "anchored_paths": ["db/migrations/001.sql"]},
        ]
        result = rank_lessons(lessons, ["src/auth/token.py"], "fix authentication token")
        assert len(result) > 0
        assert result[0]["title"] == "Auth bugfix"
        print(json.dumps({"status": "ok"}))
        return 0

    data = json.load(sys.stdin)
    result = rank_lessons(
        data.get("lessons", []),
        data.get("changed_files", []),
        data.get("task_description", ""),
        data.get("max_lessons", 8),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
