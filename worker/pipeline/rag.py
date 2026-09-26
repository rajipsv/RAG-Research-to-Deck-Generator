"""Multi-query retrieval with score-based re-ranking.

Re-ranking here means: run several differently-angled queries against the
same topic, retrieve candidates per query, then keep each chunk's *best*
similarity score across all queries and sort by that — so a chunk that is
only weakly related to the main topic string but strongly matches one
specific angle (e.g. "limitations") still surfaces, while chunks that only
looked relevant by accident don't dominate just because they showed up in
every query.
"""

from __future__ import annotations

import json
import os

import cohere

from embeddings import embed_query
from db import search_similar

SUBQUERY_MODEL = "command-r-plus-08-2024"

SUBQUERY_ANGLES = [
    "core methods and approaches",
    "key results and findings",
    "real-world applications",
    "limitations and open problems",
]


def generate_subqueries(topic: str) -> list[str]:
    """Ask Cohere for angle-specific search queries; fall back to fixed angles on failure."""
    client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    prompt = (
        f"Topic: {topic}\n\n"
        "Write 4 short search queries (3-6 words each) that would each surface "
        "a different angle of academic literature on this topic: methods, "
        "results, applications, and limitations. Return ONLY a JSON array of "
        "4 strings, nothing else."
    )
    try:
        response = client.chat(
            model=SUBQUERY_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.message.content[0].text.strip()
        queries = json.loads(text)
        if isinstance(queries, list) and len(queries) >= 2:
            return [str(q) for q in queries[:4]]
    except Exception:
        pass
    return [f"{topic} {angle}" for angle in SUBQUERY_ANGLES]


def multi_query_retrieve(
    conn,
    topic: str,
    subqueries: list[str],
    top_k: int = 14,
    per_query_limit: int = 10,
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

    ranked = sorted(best_by_chunk.values(), key=lambda r: r["score"], reverse=True)
    return ranked[:top_k]
