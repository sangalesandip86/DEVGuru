"""Dependency-free BM25 search for Historical Task Intelligence.

Ranks historical tasks/evidence by relevance to a query.
Pure Python, stdlib only.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def bm25_search(
    query: str,
    corpus: list[dict[str, Any]],
    content_key: str = "content",
    k1: float = 1.5,
    b: float = 0.75,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Rank corpus items by BM25 relevance to query.

    Each corpus item must have a ``content_key`` field (default "content").
    Returns up to ``top_n`` items, highest relevance first, with ``relevance_score`` added.
    """
    if not query or not corpus:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    doc_tokens = [tokenize(str(doc.get(content_key, ""))) for doc in corpus]
    n = len(corpus)
    avg_dl = sum(len(d) for d in doc_tokens) / n if n else 1.0

    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    results: list[tuple[float, int]] = []
    for idx, tokens in enumerate(doc_tokens):
        tf = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for qt in query_tokens:
            if qt not in df:
                continue
            idf = math.log((n - df[qt] + 0.5) / (df[qt] + 0.5) + 1.0)
            term_tf = tf.get(qt, 0)
            numerator = term_tf * (k1 + 1)
            denominator = term_tf + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator
        if score > 0:
            results.append((score, idx))

    results.sort(key=lambda x: -x[0])
    out = []
    for score, idx in results[:top_n]:
        item = {**corpus[idx], "relevance_score": round(score, 4)}
        out.append(item)
    return out
