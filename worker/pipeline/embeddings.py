"""Embedding client — Cohere.

Swapped in for Voyage AI: Voyage throttles accounts without a payment
method to 3 requests/min, which made a ~50-paper run painfully slow even
with retries. Cohere's trial API key needs no payment method and isn't
throttled the same way. Requires COHERE_API_KEY.

embed-english-v3.0 is 1024-dim; must match scripts/migrate.sql's
vector(1024).
"""

from __future__ import annotations

import os

import cohere

MODEL = "embed-english-v3.0"

_client: cohere.ClientV2 | None = None


def get_client() -> cohere.ClientV2:
    global _client
    if _client is None:
        _client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    result = get_client().embed(
        texts=texts,
        model=MODEL,
        input_type="search_document",
        embedding_types=["float"],
    )
    return result.embeddings.float_


def embed_query(text: str) -> list[float]:
    result = get_client().embed(
        texts=[text],
        model=MODEL,
        input_type="search_query",
        embedding_types=["float"],
    )
    return result.embeddings.float_[0]
