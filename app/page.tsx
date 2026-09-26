"use client";

import { useEffect, useRef, useState } from "react";

type PipelineResult = {
  filename: string;
  paperCount: number;
  slideCount: number;
  downloadUrl: string;
};

type StatusResponse =
  | { state: "waiting" | "active" | "delayed"; progress: number | { stage?: string } }
  | { state: "completed"; result: PipelineResult; downloadUrl: string }
  | { state: "failed"; error: string | null }
  | { error: string };

const STAGE_LABELS: Record<string, string> = {
  "ingestion:start": "Fetching papers from OpenAlex…",
  "ingestion:done": "Papers fetched and embedded.",
  "rag:start": "Running multi-query retrieval…",
  "rag:done": "Findings ranked.",
  "synthesis:start": "Claude is writing the slides…",
  "synthesis:done": "Slide content ready.",
  "assembly:start": "Assembling the .pptx…",
  "assembly:done": "Deck complete.",
};

function stageLabel(progress: number | { stage?: string } | undefined): string {
  if (!progress || typeof progress === "number") return "Queued…";
  const stage = progress.stage;
  if (!stage) return "Working…";
  return STAGE_LABELS[stage] ?? stage;
}

export default function Home() {
  const [topic, setTopic] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        const data: StatusResponse = await res.json();
        setStatus(data);
        if ("state" in data && (data.state === "completed" || data.state === "failed")) {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // transient network hiccup — next tick will retry
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim() || submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    setStatus(null);
    setJobId(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: topic.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSubmitError(data.error ?? "Something went wrong.");
        return;
      }
      setJobId(String(data.jobId));
    } catch {
      setSubmitError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  }

  const isDone = status && "state" in status && status.state === "completed";
  const isFailed = status && "state" in status && status.state === "failed";
  const isWorking = jobId && !isDone && !isFailed;

  return (
    <main>
      <h1>Research-to-Deck Generator</h1>
      <p className="subtitle">
        Give it a research topic. It pulls 50+ papers from OpenAlex, runs
        multi-query RAG over them, and has Claude assemble a cited, branded
        slide deck.
      </p>

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="e.g. retrieval augmented generation"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          disabled={submitting || Boolean(isWorking)}
        />
        <button type="submit" disabled={submitting || Boolean(isWorking) || !topic.trim()}>
          {submitting ? "Starting…" : "Generate deck"}
        </button>
      </form>

      {submitError && <p className="error" style={{ marginTop: 16 }}>{submitError}</p>}

      {jobId && (
        <div className="status">
          {isFailed && "error" in status! && (
            <p className="error">
              Generation failed: {(status as { error: string | null }).error ?? "unknown error"}
            </p>
          )}

          {isDone && "result" in status! && (
            <>
              <p>Deck ready — {status.result.paperCount} papers, {status.result.slideCount} slides.</p>
              <a className="download" href={status.downloadUrl} download>
                Download .pptx
              </a>
            </>
          )}

          {isWorking && (
            <div className="status-row">
              <span className="spinner" />
              <span>
                {stageLabel(status && "progress" in status ? status.progress : undefined)}
              </span>
            </div>
          )}

          <p className="meta">Job ID: {jobId}</p>
        </div>
      )}

      <footer>
        Or use the API directly: <code>POST /api/generate</code>,{" "}
        <code>GET /api/status/:jobId</code>, <code>GET /api/download/:jobId</code>.
      </footer>
    </main>
  );
}
