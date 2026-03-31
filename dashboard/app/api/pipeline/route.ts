import { getPipelineStatus, triggerPipelineRun } from "@/lib/pipeline-api";

export async function GET() {
  try {
    const status = await getPipelineStatus();
    return Response.json(status);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}

export async function POST() {
  try {
    const result = await triggerPipelineRun();
    return Response.json(result);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
