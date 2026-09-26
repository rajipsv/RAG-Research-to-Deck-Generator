import { NextRequest, NextResponse } from "next/server";
import { getDeckQueue, PipelineResult } from "@/lib/queue";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  const job = await getDeckQueue().getJob(jobId);

  if (!job || (await job.getState()) !== "completed") {
    return NextResponse.json({ error: "Deck is not ready yet." }, { status: 404 });
  }

  const result = job.returnvalue as PipelineResult;
  if (!result.downloadUrl) {
    return NextResponse.json({ error: "Deck file is missing." }, { status: 404 });
  }

  // The worker (Fly) uploaded the .pptx to Vercel Blob since it doesn't
  // share a filesystem with this (Vercel) API process; just hand the client
  // straight to it.
  return NextResponse.redirect(result.downloadUrl);
}
