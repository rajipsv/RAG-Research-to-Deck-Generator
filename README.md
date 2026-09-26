# Research-to-Deck Generator

Given a research topic, this pulls 50+ papers from OpenAlex, runs
multi-query RAG with re-ranking over them, has Claude synthesize slide
content with citations, and assembles a branded `.pptx` (with speaker
notes) — triggered by a Next.js API route and downloadable via a link.

## Architecture

```
POST /api/generate {topic}
        │
        ▼
  BullMQ queue (Redis)  ──▶  worker/index.ts (Node)
                                  │ spawns
                                  ▼
                    worker/pipeline/run_pipeline.py
                    ├─ openalex.py          → fetch papers (abstracts)
                    ├─ ingestion.py         → chunk text
                    ├─ embeddings.py        → Voyage AI embeddings
                    ├─ db.py                → Postgres + pgvector
                    ├─ rag.py               → multi-query retrieval + re-rank
                    ├─ synthesis.py         → Claude → slide JSON + citations
                    └─ deck.py              → python-pptx → branded .pptx
        │
        ▼
GET /api/status/:jobId  →  { state, progress, downloadUrl }
GET /api/download/:jobId → redirects to the .pptx (Vercel Blob)
```

The API layer (Node/Next.js, deployable to Vercel) and the pipeline worker
(Node + Python, must run somewhere that supports long-lived processes —
Vercel serverless functions can't host it) are deliberately split. Run the
worker locally with `npm run worker` for now; see "Known limitations" below
before deploying it anywhere.

## Deviations from a literal reading of the spec (and why)

- **Abstracts, not full PDF text.** Not all OpenAlex results have an
  open-access PDF, and PDF text extraction is unreliable (paywalls, scans,
  broken layout). Abstracts are available for the large majority of results
  and are already dense summaries, which suits RAG-over-findings well.
  OpenAlex stores abstracts as a word-position inverted index rather than
  plain text; `openalex.py` reconstructs the text before it reaches the rest
  of the pipeline. `ingestion.py`'s `chunk_text` already handles longer text
  if full-text extraction is added later via `primary_location.pdf_url`.
- **Voyage AI for embeddings**, not a local model. This is Anthropic's own
  recommended embedding pairing for Claude, and it avoids a multi-GB
  `sentence-transformers`/`torch` download just to stand the project up.
  This does mean a second required API key (`VOYAGE_API_KEY`) beyond
  `ANTHROPIC_API_KEY`.
- **Re-ranking is score-based, not a separate cross-encoder model.**
  `rag.py` runs several angle-specific sub-queries (methods, results,
  applications, limitations) and keeps each chunk's *best* score across all
  of them — this is what "multi-query retrieval with re-ranking" means here.
  A dedicated cross-encoder re-ranker could be swapped in later without
  changing the interface.

## Local setup

**Prerequisites:** Node 20+, Python 3.11+, Docker (for local Postgres/Redis).

```bash
# 1. Install Node dependencies
npm install

# 2. Create and populate a Python virtualenv for the pipeline
python -m venv .venv
./.venv/Scripts/pip install -r worker/pipeline/requirements.txt   # Windows
# source .venv/bin/activate && pip install -r worker/pipeline/requirements.txt  # macOS/Linux

# 3. Start Postgres (with pgvector) and Redis
docker compose up -d

# 4. Apply the DB schema
docker compose exec -T postgres psql -U postgres -d research_deck -f - < scripts/migrate.sql

# 5. Configure environment
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY (required).
# Set PYTHON_BIN to your venv's python if it's not the first "python" on PATH,
# e.g. PYTHON_BIN=./.venv/Scripts/python.exe (Windows) or ./.venv/bin/python (macOS/Linux)

# 6. Run the app (two terminals)
npm run dev      # Next.js API on http://localhost:3000
npm run worker   # BullMQ worker — restart this after changing .env
```

## Using it

```bash
curl -X POST http://localhost:3000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "retrieval augmented generation"}'
# => {"jobId": "1"}

curl http://localhost:3000/api/status/1
# => {"state": "active", "progress": {"stage": "rag:start"}}
# ... poll until:
# => {"state": "completed", "downloadUrl": "/api/download/1", "result": {...}}

curl -o deck.pptx http://localhost:3000/api/download/1
```

A run takes a few minutes: fetching 50+ papers from OpenAlex (faster with
`OPENALEX_MAILTO` set, since that uses the polite pool), embedding all of
them, then two Claude calls.

## Deploying the worker to Fly.io

The Next.js API layer deploys to Vercel as-is. The worker (`worker/index.ts`
+ the Python pipeline) needs an always-on process, which this repo now
scaffolds for Fly.io via the root `Dockerfile` and `fly.toml`.

Since the API (Vercel) and worker (Fly) are different hosts, three pieces of
shared infrastructure need to be reachable from both — or, for Postgres,
from the worker specifically:

| Piece | Needs to be reachable from | Suggested option |
|---|---|---|
| Redis (BullMQ) | Vercel **and** Fly | [Upstash Redis](https://upstash.com) (public, TLS) |
| Postgres (pgvector) | Fly only | Fly Postgres, or any hosted Postgres with the `pgvector` extension |
| Generated `.pptx` files | Vercel reads what Fly wrote | Vercel Blob (already wired up — see below) |

Local `docker-compose` Postgres/Redis are `localhost`-only and won't work
for this; swap `DATABASE_URL`/`REDIS_URL` for the hosted equivalents above
before deploying.

```bash
# 1. Register the Fly app (edit `app =` in fly.toml to match what you pick,
#    or let this command fill it in for you)
fly apps create <a-unique-name>

# 2. Set secrets (same values as .env, but pointing at hosted services)
fly secrets set \
  ANTHROPIC_API_KEY=... \
  VOYAGE_API_KEY=... \
  DATABASE_URL=postgresql://... \
  REDIS_URL=rediss://... \
  BLOB_READ_WRITE_TOKEN=...

# 3. Deploy (run from the repo root — the Dockerfile needs lib/ and
#    package.json alongside worker/)
fly deploy
```

Also set `REDIS_URL` (and `BLOB_READ_WRITE_TOKEN`, if you didn't create the
Blob store from the Vercel dashboard, which sets it automatically) on the
**Vercel** project so the API can enqueue jobs and check their status on the
same Redis the worker is consuming from.

`BLOB_READ_WRITE_TOKEN` is what makes the file handoff work: the worker
uploads the finished `.pptx` to Vercel Blob and returns its public URL as
part of the job result; `GET /api/download/:jobId` just redirects there
instead of reading local disk (which only worked when the API and worker
were the same process on the same machine).
- **Not run end-to-end with real credentials in this environment** — there
  was no `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` available here. Verified
  instead, piece by piece, with real infrastructure and real network calls
  where no credential was required:
  - Real OpenAlex fetch (`openalex.fetch_papers`) — confirmed against the
    live API.
  - Real Postgres/pgvector round trip (insert real fetched papers, similarity
    search) — confirmed against the dockerized DB. This caught and fixed a
    real bug: embeddings must be wrapped in `pgvector.Vector(...)`, not
    passed as plain Python lists, or Postgres has no `<=>` operator for them.
  - Deck assembly (`deck.build_deck`) — confirmed by generating a real
    `.pptx` from mock slide data and reading it back (correct slide count,
    titles, bullets with citation markers, speaker notes, references slide).
  - The full request path — confirmed by submitting a real job through
    `POST /api/generate` and watching it correctly fail with a clean,
    surfaced error at the Voyage embedding call (the first step that needs a
    credential this environment doesn't have), with progress (`ingestion:start`)
    correctly reported along the way, and no partial rows left in the
    database (the ingestion loop only commits once, at the end).
  - Add `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` to `.env`, restart the
    worker, and resubmit to complete verification of the RAG, synthesis, and
    full-deck-download steps.
- **Deck branding is a fixed, hardcoded theme** (`worker/pipeline/deck.py`:
  colors, fonts, accent bar). It's a real branded look, not python-pptx
  defaults, but it isn't yet configurable per-project.
