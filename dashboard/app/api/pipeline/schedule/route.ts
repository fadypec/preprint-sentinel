import { NextRequest } from "next/server";
import { updatePipelineSchedule } from "@/lib/pipeline-api";

export async function PUT(request: NextRequest) {
  try {
    const { hour, minute } = await request.json();
    const result = await updatePipelineSchedule(hour, minute ?? 0);
    return Response.json(result);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
