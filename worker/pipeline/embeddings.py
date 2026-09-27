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
import time

import cohere
from cohere.errors import TooManyRequestsError

MODEL = "embed-english-v3.0"
MAX_TEXTS_PER_CALL = 96  # Cohere embed endpoint's hard limit per request
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 8.0  # trial keys are limited per-minute; a few short waits clears it

_client: cohere.ClientV2 | None = None


def get_client() -> cohere.ClientV2:
    global _client
    if _client is None:
        _client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    return _client


def _embed_with_retry(client: cohere.ClientV2, **kwargs):
    """Full-text ingestion can push a trial key's per-minute token budget
    over the edge; retry with backoff instead of failing the whole run."""
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(MAX_RETRIES):
        try:
            return client.embed(**kwargs)
        except TooManyRequestsError:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(backoff)
            backoff *= 2


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed `texts`, batching at MAX_TEXTS_PER_CALL — a full-text paper can
    chunk into far more than one call's worth."""
    if not texts:
        return []
    client = get_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), MAX_TEXTS_PER_CALL):
        batch = texts[i : i + MAX_TEXTS_PER_CALL]
        result = _embed_with_retry(
            client,
            texts=batch,
            model=MODEL,
            input_type="search_document",
            embedding_types=["float"],
        )
        vectors.extend(result.embeddings.float_)
    return vectors


def embed_query(text: str) -> list[float]:
    result = _embed_with_retry(
        get_client(),
        texts=[text],
        model=MODEL,
        input_type="search_query",
        embedding_types=["float"],
    )
    return result.embeddings.float_[0]
