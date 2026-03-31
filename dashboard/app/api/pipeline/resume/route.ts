import { resumePipeline } from "@/lib/pipeline-api";

export async function POST() {
  try {
    const result = await resumePipeline();
    return Response.json(result);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
