import { Worker, Job } from "bullmq";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import IORedis from "ioredis";
import { QUEUE_NAME, PipelineResult } from "../lib/queue";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const connection = new IORedis(process.env.REDIS_URL || "redis://localhost:6379", {
  maxRetriesPerRequest: null,
});

const PYTHON_BIN = process.env.PYTHON_BIN || "python";
const PIPELINE_SCRIPT = path.join(__dirname, "pipeline", "run_pipeline.py");

function runPipeline(
  topic: string,
  jobId: string,
  onStage: (stage: string) => void
): Promise<PipelineResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [PIPELINE_SCRIPT, topic, jobId], {
      env: process.env,
    });

    let stdout = "";
    let stderrTail = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderrTail += text;
      for (const rawLine of text.split("\n")) {
        const line = rawLine.trim();
        if (!line) continue;
        if (line.startsWith("STAGE:")) {
          onStage(line.slice("STAGE:".length));
        } else {
          console.error(`[pipeline ${jobId}]`, line);
        }
      }
    });

    child.on("error", reject);

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`pipeline exited with code ${code}: ${stderrTail.slice(-2000)}`));
        return;
      }
      const lastLine = stdout.trim().split("\n").filter(Boolean).pop();
      if (!lastLine) {
        reject(new Error("pipeline produced no output"));
        return;
      }
      try {
        resolve(JSON.parse(lastLine) as PipelineResult);
      } catch {
        reject(new Error(`could not parse pipeline output as JSON: ${lastLine}`));
      }
    });
  });
}

const worker = new Worker(
  QUEUE_NAME,
  async (job: Job) => {
    const { topic } = job.data as { topic: string };
    return runPipeline(topic, String(job.id), (stage) => {
      job.updateProgress({ stage });
    });
  },
  { connection, concurrency: 1 }
);

worker.on("completed", (job) => {
  console.log(`[worker] job ${job.id} completed:`, job.returnvalue);
});

worker.on("failed", (job, err) => {
  console.error(`[worker] job ${job?.id} failed:`, err.message);
});

console.log(`[worker] listening on queue "${QUEUE_NAME}" (python: ${PYTHON_BIN})`);
