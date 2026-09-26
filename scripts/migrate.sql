-- Schema for the Research-to-Deck Generator's RAG store.
-- Run with: psql "$DATABASE_URL" -f scripts/migrate.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
  paper_id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  title TEXT,
  abstract TEXT,
  year INT,
  authors TEXT,
  url TEXT
);

-- Cohere embed-english-v3.0 embeddings are 1024-dimensional; update this if you swap models.
CREATE TABLE IF NOT EXISTS chunks (
  id SERIAL PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
  ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS chunks_paper_id_idx ON chunks (paper_id);
CREATE INDEX IF NOT EXISTS papers_topic_idx ON papers (topic);
