"""Postgres/pgvector access layer."""

from __future__ import annotations

import os

import psycopg2
import psycopg2.extensions
from pgvector import Vector
from pgvector.psycopg2 import register_vector


def get_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def upsert_paper(conn: psycopg2.extensions.connection, topic: str, paper: dict) -> None:
    authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or []))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO papers (paper_id, topic, title, abstract, year, authors, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (paper_id) DO UPDATE SET topic = EXCLUDED.topic
            """,
            (
                paper["paperId"],
                topic,
                paper.get("title"),
                paper.get("abstract"),
                paper.get("year"),
                authors,
                paper.get("url"),
            ),
        )


def replace_chunks(
    conn: psycopg2.extensions.connection,
    paper_id: str,
    chunks: list[tuple[str, list[float]]],
) -> None:
    """Delete a paper's existing chunks and insert the given (content, embedding) pairs."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE paper_id = %s", (paper_id,))
        for idx, (content, embedding) in enumerate(chunks):
            cur.execute(
                """
                INSERT INTO chunks (paper_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (paper_id, idx, content, Vector(embedding)),
            )


def search_similar(
    conn: psycopg2.extensions.connection,
    embedding: list[float],
    topic: str,
    limit: int = 8,
) -> list[dict]:
    vector = Vector(embedding)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.content, c.paper_id, p.title, p.authors, p.year, p.url,
                   1 - (c.embedding <=> %s) AS score
            FROM chunks c
            JOIN papers p ON p.paper_id = c.paper_id
            WHERE p.topic = %s
            ORDER BY c.embedding <=> %s
            LIMIT %s
            """,
            (vector, topic, vector, limit),
        )
        cols = ["content", "paper_id", "title", "authors", "year", "url", "score"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
