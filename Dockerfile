# Runs worker/index.ts (BullMQ job consumer). It spawns the RAG/deck-assembly
# pipeline as a Python subprocess per job, so this image needs both runtimes.
# Not used by Vercel — that's the Next.js API layer, built separately.
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps in their own layer so they only rebuild when requirements.txt changes.
COPY worker/pipeline/requirements.txt worker/pipeline/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r worker/pipeline/requirements.txt
ENV PYTHON_BIN=/opt/venv/bin/python

# Node deps (tsx runs the worker directly with no build step).
COPY package.json package-lock.json ./
RUN npm ci

# Everything the worker needs at runtime: worker/ itself, the shared queue
# type in lib/, and tsconfig for path resolution. The Next.js app/ tree is
# deliberately not copied — this image never serves the API.
COPY worker worker
COPY lib lib
COPY tsconfig.json ./

RUN mkdir -p worker/output

CMD ["npm", "run", "worker:start"]
