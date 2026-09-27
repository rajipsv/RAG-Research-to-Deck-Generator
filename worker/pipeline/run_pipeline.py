"""Orchestrates one end-to-end deck generation run.

Invoked by the Node worker as:
    python run_pipeline.py "<topic>" "<job_id>"

Progress is reported via `STAGE:<name>` lines on stderr (the Node worker
parses these into BullMQ job progress). The final result is a single JSON
object printed to stdout as the last line.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openalex import fetch_papers, fetch_pdf_text
from ingestion import chunk_text
from embeddings import embed_documents
from db import get_connection, upsert_paper, replace_chunks
from rag import generate_subqueries, multi_query_retrieve
from synthesis import synthesize_deck
from deck import build_deck


def log_stage(name: str) -> None:
    print(f"STAGE:{name}", file=sys.stderr, flush=True)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: run_pipeline.py <topic> <job_id>", file=sys.stderr)
        sys.exit(1)

    topic = sys.argv[1]
    job_id = sys.argv[2]

    log_stage("ingestion:start")
    papers = fetch_papers(topic)
    if len(papers) < 10:
        print(
            f"WARN: only found {len(papers)} papers with abstracts for topic '{topic}'",
            file=sys.stderr,
        )
    if not papers:
        raise RuntimeError(f"No papers with abstracts found for topic '{topic}'.")

    conn = get_connection()
    try:
        for paper in papers:
            upsert_paper(conn, topic, paper)
            full_text = fetch_pdf_text(paper["pdfUrl"]) if paper.get("pdfUrl") else None
            chunks = chunk_text(full_text or paper.get("abstract") or "")
            if not chunks:
                continue
            vectors = embed_documents(chunks)
            replace_chunks(conn, paper["paperId"], list(zip(chunks, vectors)))
        conn.commit()
        log_stage("ingestion:done")

        log_stage("rag:start")
        subqueries = generate_subqueries(topic)
        findings = multi_query_retrieve(conn, topic, subqueries, top_k=25)
        log_stage("rag:done")
    finally:
        conn.close()

    log_stage("synthesis:start")
    deck_data = synthesize_deck(topic, findings)
    log_stage("synthesis:done")

    log_stage("assembly:start")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{job_id}.pptx"
    output_path = os.path.abspath(os.path.join(output_dir, filename))
    build_deck(deck_data, topic, output_path)
    log_stage("assembly:done")

    print(
        json.dumps(
            {
                "filename": filename,
                "paperCount": len(papers),
                "slideCount": len(deck_data["slides"]) + 1 + _ref_slide_count(deck_data),
            }
        )
    )


def _ref_slide_count(deck_data: dict) -> int:
    ref_count = len(deck_data.get("references", []))
    return max(1, (ref_count + 9) // 10)


if __name__ == "__main__":
    main()
