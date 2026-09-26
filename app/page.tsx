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

const EXAMPLE_TOPICS = [
  "retrieval augmented generation",
  "diffusion models for images",
  "mixture of experts",
  "in-context learning",
];

const PHASES = [
  { label: "Ingestion", sub: "Fetching papers from OpenAlex" },
  { label: "Retrieval", sub: "Multi-query RAG + re-rank" },
  { label: "Synthesis", sub: "Claude is writing the slides" },
  { label: "Assembly", sub: "Assembling the branded .pptx" },
];

const ORDERED_STAGES = [
  "ingestion:start",
  "ingestion:done",
  "rag:start",
  "rag:done",
  "synthesis:start",
  "synthesis:done",
  "assembly:start",
  "assembly:done",
];

function currentStageIndex(progress: number | { stage?: string } | undefined): number {
  if (!progress || typeof progress === "number") return -1;
  return ORDERED_STAGES.indexOf(progress.stage ?? "");
}

function phaseStatus(phaseIdx: number, stageIdx: number): "done" | "active" | "pending" {
  if (stageIdx < 0) return "pending";
  const donePos = phaseIdx * 2 + 1;
  if (stageIdx >= donePos) return "done";
  if (stageIdx >= phaseIdx * 2) return "active";
  return "pending";
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M20 6 9 17l-5-5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path d="M12 2v6M12 16v6M2 12h6M16 12h6M4.9 4.9l4.2 4.2M14.9 14.9l4.2 4.2M19.1 4.9l-4.2 4.2M9.1 14.9l-4.2 4.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function LayersIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path d="M12 2 2 7l10 5 10-5-10-5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function FileTextIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M14 2v6h6M9 13h6M9 17h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const STEP_STATUS_LABEL: Record<string, string> = {
  done: "done",
  active: "active",
  pending: "pending",
};

function stageLabel(progress: number | { stage?: string } | undefined): string {
  const idx = currentStageIndex(progress);
  if (idx < 0) return "Waiting for a worker to pick this up…";
  const phase = PHASES[Math.floor(idx / 2)];
  return phase?.sub ?? "Working…";
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

  async function submitTopic(value: string) {
    if (!value.trim() || submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    setStatus(null);
    setJobId(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: value.trim() }),
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submitTopic(topic);
  }

  function handleChipClick(example: string) {
    setTopic(example);
    submitTopic(example);
  }

  const isDone = status && "state" in status && status.state === "completed";
  const isFailed = status && "state" in status && status.state === "failed";
  const isWorking = jobId && !isDone && !isFailed;
  const stageIdx = isWorking ? currentStageIndex(status && "progress" in status ? status.progress : undefined) : -1;

  return (
    <main>
      <span className="eyebrow">
        <span className="eyebrow-dot" />
        RAG-powered
      </span>

      <h1>Research-to-Deck Generator</h1>
      <p className="subtitle">
        Give it a research topic. It pulls 50+ papers from OpenAlex, runs
        multi-query RAG over them, and has Claude assemble a cited, branded
        slide deck — automatically.
      </p>

      <div className="features">
        <div className="feature">
          <div className="feature-icon"><LayersIcon /></div>
          <p className="feature-title">Multi-query RAG</p>
          <p className="feature-desc">Angle-specific retrieval with score re-ranking.</p>
        </div>
        <div className="feature">
          <div className="feature-icon"><SparkIcon /></div>
          <p className="feature-title">Claude synthesis</p>
          <p className="feature-desc">Slide titles, bullets, and citations.</p>
        </div>
        <div className="feature">
          <div className="feature-icon"><FileTextIcon /></div>
          <p className="feature-title">Branded .pptx</p>
          <p className="feature-desc">Speaker notes and a references slide.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="input-wrap">
          <input
            type="text"
            placeholder="e.g. retrieval augmented generation"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={submitting || Boolean(isWorking)}
          />
        </div>
        <button type="submit" disabled={submitting || Boolean(isWorking) || !topic.trim()}>
          {submitting ? "Starting…" : "Generate deck"}
        </button>
      </form>

      <div className="chips">
        {EXAMPLE_TOPICS.map((example) => (
          <button
            key={example}
            type="button"
            className="chip"
            disabled={submitting || Boolean(isWorking)}
            onClick={() => handleChipClick(example)}
          >
            {example}
          </button>
        ))}
      </div>

      {submitError && (
        <div className="status">
          <div className="error-box">
            <AlertIcon />
            <span>{submitError}</span>
          </div>
        </div>
      )}

      {jobId && (
        <div className="status">
          {isFailed && "error" in status! && (
            <div className="error-box">
              <AlertIcon />
              <span>
                Generation failed: {(status as { error: string | null }).error ?? "unknown error"}
              </span>
            </div>
          )}

          {isDone && "result" in status! && (
            <>
              <div className="result-heading">
                <span className="result-icon"><CheckIcon /></span>
                <p className="result-title">Deck ready</p>
              </div>
              <div className="stat-row">
                <div className="stat">
                  <div className="stat-value">{status.result.paperCount}</div>
                  <div className="stat-label">Papers</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{status.result.slideCount}</div>
                  <div className="stat-label">Slides</div>
                </div>
              </div>
              <a className="download" href={status.downloadUrl} download>
                <DownloadIcon />
                Download .pptx
              </a>
            </>
          )}

          {isWorking && (
            <>
              <div className="steps">
                {PHASES.map((phase, i) => {
                  const st = phaseStatus(i, stageIdx);
                  return (
                    <div className="step" key={phase.label}>
                      <span className={`step-line ${st !== "pending" ? "filled" : ""}`} />
                      <span className={`step-dot ${st}`} title={STEP_STATUS_LABEL[st]}>
                        {st === "done" ? <CheckIcon /> : i + 1}
                      </span>
                      <span className="step-label">{phase.label}</span>
                    </div>
                  );
                })}
              </div>
              <p className="step-sub">
                {stageLabel(status && "progress" in status ? status.progress : undefined)}
              </p>
            </>
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
