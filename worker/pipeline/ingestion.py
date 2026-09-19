"""Text chunking for ingested paper content."""

from __future__ import annotations

import re


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """Split `text` into overlapping windows of at most `max_chars` characters.

    Abstracts are typically short enough to come back as a single chunk;
    this still handles longer text (e.g. full-text extracts added later)
    without a rewrite.
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = start + max_chars
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = end - overlap
    return chunks
