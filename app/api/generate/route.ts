import { NextRequest, NextResponse } from "next/server";
import { getDeckQueue } from "@/lib/queue";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Request body must be JSON." },
      { status: 400 }
    );
  }

  const topic = (body as { topic?: unknown } | null)?.topic;
  if (typeof topic !== "string" || !topic.trim()) {
    return NextResponse.json(
      { error: "Body must include a non-empty 'topic' string." },
      { status: 400 }
    );
  }

  const job = await getDeckQueue().add("generate-deck", { topic: topic.trim() });

  return NextResponse.json({ jobId: job.id }, { status: 202 });
}
