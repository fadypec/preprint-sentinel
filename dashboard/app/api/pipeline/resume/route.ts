import { resumePipeline } from "@/lib/pipeline-api";
import { apiRequireAdmin } from "@/lib/auth-guard";

export async function POST() {
  const denied = await apiRequireAdmin();
  if (denied) return denied;
  try {
    const result = await resumePipeline();
    return Response.json(result);
  } catch {
    return Response.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
