"""OpenAlex paper search.

Uses the OpenAlex Works API's search endpoint. OpenAlex doesn't return
plain abstract text — it returns an "inverted index" (word -> positions),
presumably to save bandwidth — so we reconstruct the text before handing
results back. Output is normalized to a shape the rest of the pipeline
expects (paperId, title, abstract, pdfUrl, year, authors, url).

Where an open-access PDF is available (`primary_location.pdf_url`), the
pipeline fetches and extracts its full text for ingestion instead of just
the abstract — see `fetch_pdf_text`. This is deliberately best-effort: PDF
download + extraction is unreliable (paywalls, scanned images, broken
layouts), so any failure just falls back to the abstract rather than
failing the run.
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Optional

import requests
from pypdf import PdfReader

# Most pdf_url links resolve to an HTML landing page (paywall, cookie
# banner, redirect) rather than a raw PDF — that's expected and handled by
# fetch_pdf_text's fallback to the abstract, so pypdf's per-failure warnings
# would just spam the worker's logs across most of a 60-paper run.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

BASE_URL = "https://api.openalex.org/works"
SELECT_FIELDS = "id,title,abstract_inverted_index,publication_year,authorships,primary_location,doi"
MAX_CONSECUTIVE_RATE_LIMITS = 6  # ~6-30s of backoff before giving up on this page
PDF_FETCH_TIMEOUT = 20
PDF_MAX_PAGES = 40


def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
    """Turn {"word": [pos, ...], ...} back into a plain-text abstract."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    max_pos = -1
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
            max_pos = max(max_pos, i)
    return " ".join(positions.get(i, "") for i in range(max_pos + 1))


def _normalize(work: dict) -> dict:
    authors = [
        {"name": a["author"]["display_name"]}
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    primary_location = work.get("primary_location") or {}
    url = primary_location.get("landing_page_url") or work.get("doi")
    return {
        "paperId": work.get("id"),
        "title": work.get("title"),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "pdfUrl": primary_location.get("pdf_url"),
        "year": work.get("publication_year"),
        "authors": authors,
        "url": url,
    }


def fetch_pdf_text(pdf_url: str) -> Optional[str]:
    """Download a PDF and extract its text. Returns None on any failure —
    full text is a bonus on top of the abstract, never a hard requirement."""
    try:
        resp = requests.get(
            pdf_url,
            timeout=PDF_FETCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (research-deck-worker)"},
        )
        resp.raise_for_status()
        reader = PdfReader(io.BytesIO(resp.content))
        pages = reader.pages[:PDF_MAX_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages)
        # pypdf occasionally emits NUL bytes from malformed font/encoding
        # tables — Postgres text columns reject them outright (ValueError:
        # "A string literal cannot contain NUL characters"), so strip them
        # here rather than downstream at every consumer.
        text = text.replace("\x00", "").strip()
        return text or None
    except Exception:
        return None


def fetch_papers(
    topic: str,
    target_count: int = 60,
    page_size: int = 100,
) -> list[dict]:
    """Fetch up to `target_count` papers for `topic` that have an abstract.

    Returns whatever was collected so far if persistently rate-limited,
    rather than retrying forever. Set `OPENALEX_MAILTO` to an email address
    to use OpenAlex's faster, opt-in "polite pool" (see
    https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication).
    """
    mailto = os.environ.get("OPENALEX_MAILTO")
    params_base = {"search": topic, "per_page": page_size, "select": SELECT_FIELDS}
    if mailto:
        params_base["mailto"] = mailto

    papers: list[dict] = []
    seen_ids: set[str] = set()
    cursor = "*"
    consecutive_rate_limits = 0

    while len(papers) < target_count and cursor:
        params = {**params_base, "cursor": cursor}
        resp = requests.get(BASE_URL, params=params, timeout=30)
        if resp.status_code == 429:
            consecutive_rate_limits += 1
            if consecutive_rate_limits > MAX_CONSECUTIVE_RATE_LIMITS:
                break
            time.sleep(2.0 * consecutive_rate_limits)
            continue
        consecutive_rate_limits = 0
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("results", [])
        if not batch:
            break

        for work in batch:
            paper_id = work.get("id")
            if not paper_id or paper_id in seen_ids:
                continue
            if not work.get("abstract_inverted_index"):
                continue
            seen_ids.add(paper_id)
            papers.append(_normalize(work))
            if len(papers) >= target_count:
                break

        cursor = payload.get("meta", {}).get("next_cursor")
        if not mailto:
            time.sleep(0.15)  # be polite to the shared/common pool

    return papers[:target_count]
