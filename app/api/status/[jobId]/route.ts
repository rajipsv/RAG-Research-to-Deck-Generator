import { NextRequest, NextResponse } from "next/server";
import { getDeckQueue, PipelineResult } from "@/lib/queue";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  const job = await getDeckQueue().getJob(jobId);

  if (!job) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }

  const state = await job.getState();

  if (state === "completed") {
    const result = job.returnvalue as PipelineResult;
    return NextResponse.json({
      state,
      result,
      downloadUrl: `/api/download/${job.id}`,
    });
  }

  if (state === "failed") {
    return NextResponse.json({ state, error: job.failedReason });
  }

  return NextResponse.json({ state, progress: job.progress });
}
