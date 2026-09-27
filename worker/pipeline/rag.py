"""Multi-query retrieval with query expansion and a cross-encoder re-rank.

Two distinct steps happen here, and they're not the same kind of
"re-ranking":

1. Fusion (in `multi_query_retrieve`): run several differently-angled
   queries against the same topic, retrieve candidates per query, then keep
   each chunk's *best* similarity score across all queries — so a chunk
   that's only weakly related to the main topic string but strongly matches
   one specific angle (e.g. "limitations") still surfaces, while chunks
   that only looked relevant by accident don't dominate just because they
   showed up in every query. This still only ever compares independently
   computed embeddings.

2. Re-rank (in `_rerank`): the fused pool is then scored against the
   original topic by Cohere's `rerank-v3.5`, a cross-encoder that judges
   each (query, chunk) pair jointly rather than by comparing two separately
   embedded vectors — strictly more accurate than step 1's cosine fusion,
   at the cost of one extra API call.
"""

from __future__ import annotations

import json
import os
import re

import cohere

import gemini
from embeddings import embed_query
from db import search_similar

RERANK_MODEL = "rerank-v3.5"

SUBQUERY_ANGLES = [
    "core methods and approaches",
    "key results and findings",
    "real-world applications",
    "limitations and open problems",
]


def generate_subqueries(topic: str) -> list[str]:
    """Ask Gemini for angle-specific search queries; fall back to fixed angles on failure."""
    prompt = (
        f"Topic: {topic}\n\n"
        "Write 4 short search queries (3-6 words each) that would each surface "
        "a different angle of academic literature on this topic: methods, "
        "results, applications, and limitations. Return ONLY a JSON array of "
        "4 strings, nothing else."
    )
    try:
        text = gemini.generate_text(prompt, max_output_tokens=200, json_mode=True).strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        queries = json.loads(match.group(0)) if match else json.loads(text)
        if isinstance(queries, list) and len(queries) >= 2:
            return [str(q) for q in queries[:4]]
    except Exception:
        pass
    return [f"{topic} {angle}" for angle in SUBQUERY_ANGLES]


def _rerank(topic: str, pooled: list[dict], top_k: int) -> list[dict]:
    """Cross-encoder re-rank of the fused pool; falls back to the pool's
    existing fusion-score order if the rerank call fails for any reason."""
    if not pooled:
        return []
    try:
        client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
        response = client.rerank(
            model=RERANK_MODEL,
            query=topic,
            documents=[r["content"] for r in pooled],
            top_n=min(top_k, len(pooled)),
        )
        return [pooled[result.index] for result in response.results]
    except Exception:
        ranked = sorted(pooled, key=lambda r: r["score"], reverse=True)
        return ranked[:top_k]


def multi_query_retrieve(
    conn,
    topic: str,
    subqueries: list[str],
    top_k: int = 25,
    per_query_limit: int = 14,
) -> list[dict]:
    best_by_chunk: dict[tuple[str, str], dict] = {}

    for query in subqueries:
        query_embedding = embed_query(query)
        results = search_similar(conn, query_embedding, topic, limit=per_query_limit)
        for result in results:
            key = (result["paper_id"], result["content"][:80])
            existing = best_by_chunk.get(key)
            if existing is None or result["score"] > existing["score"]:
                best_by_chunk[key] = result

    return _rerank(topic, list(best_by_chunk.values()), top_k)
