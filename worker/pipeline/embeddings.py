"""Embedding client — Voyage AI (Anthropic's recommended embedding provider).

Chosen over a local sentence-transformers model to keep setup fast (no
multi-gigabyte model download) and because Claude + Voyage is the pairing
Anthropic documents for RAG. Requires VOYAGE_API_KEY.
"""

from __future__ import annotations

import os

import voyageai

MODEL = "voyage-3-lite"  # 512-dim; must match scripts/migrate.sql's vector(512)

_client: voyageai.Client | None = None


def get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    result = get_client().embed(texts, model=MODEL, input_type="document")
    return result.embeddings


def embed_query(text: str) -> list[float]:
    result = get_client().embed([text], model=MODEL, input_type="query")
    return result.embeddings[0]
