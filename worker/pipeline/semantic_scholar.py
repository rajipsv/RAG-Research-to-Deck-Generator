"""Semantic Scholar paper search.

Uses the Graph API's paper-search endpoint. We fetch abstracts rather than
full PDF text: not all matching papers have an open-access PDF, and PDF
download + text extraction is unreliable enough (paywalls, scanned images,
broken layouts) that it would make ingestion the flakiest part of the
pipeline. Abstracts are available for the large majority of results and are
already dense summaries, which suits RAG-over-findings well. Swap in PDF
extraction later (via `openAccessPdf.url`) if full-text depth is needed.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "paperId,title,abstract,year,authors,url"
MAX_OFFSET = 900  # Semantic Scholar search caps offset+limit at 1000
MAX_CONSECUTIVE_RATE_LIMITS = 6  # ~6-30s of backoff before giving up on this page


def fetch_papers(
    topic: str,
    api_key: Optional[str],
    target_count: int = 60,
    page_size: int = 100,
) -> list[dict]:
    """Fetch up to `target_count` papers for `topic` that have an abstract.

    Returns whatever was collected so far if persistently rate-limited,
    rather than retrying forever.
    """
    headers = {"x-api-key": api_key} if api_key else {}
    papers: list[dict] = []
    seen_ids: set[str] = set()
    offset = 0
    consecutive_rate_limits = 0

    while len(papers) < target_count and offset <= MAX_OFFSET:
        params = {
            "query": topic,
            "fields": FIELDS,
            "limit": page_size,
            "offset": offset,
        }
        resp = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            consecutive_rate_limits += 1
            if consecutive_rate_limits > MAX_CONSECUTIVE_RATE_LIMITS:
                break
            time.sleep(2.0 * consecutive_rate_limits)
            continue
        consecutive_rate_limits = 0
        resp.raise_for_status()
        batch = resp.json().get("data", [])
        if not batch:
            break

        for paper in batch:
            paper_id = paper.get("paperId")
            if not paper_id or paper_id in seen_ids:
                continue
            if not paper.get("abstract"):
                continue
            seen_ids.add(paper_id)
            papers.append(paper)

        offset += page_size
        if not api_key:
            time.sleep(1.1)  # unauthenticated rate limit is ~1 req/sec

    return papers[:target_count]
