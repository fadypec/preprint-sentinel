import { pausePipeline } from "@/lib/pipeline-api";

export async function POST() {
  try {
    const result = await pausePipeline();
    return Response.json(result);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
