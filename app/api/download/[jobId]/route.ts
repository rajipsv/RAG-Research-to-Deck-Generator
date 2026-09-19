import { NextRequest, NextResponse } from "next/server";
import { getDeckQueue, PipelineResult } from "@/lib/queue";
import fs from "node:fs";
import path from "node:path";

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
  const filePath = path.join(process.cwd(), "worker", "output", result.filename);

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: "Deck file is missing on disk." }, { status: 404 });
  }

  const fileBuffer = fs.readFileSync(filePath);
  return new NextResponse(new Uint8Array(fileBuffer), {
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "Content-Disposition": `attachment; filename="${result.filename}"`,
    },
  });
}
