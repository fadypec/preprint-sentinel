import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const run = await prisma.pipelineRun.findFirst({
    where: { finishedAt: null },
    orderBy: { startedAt: "desc" },
  });

  if (!run) {
    return Response.json({ running: false });
  }

  return Response.json({
    running: true,
    id: run.id,
    startedAt: run.startedAt.toISOString(),
    currentStage: run.currentStage,
    papersIngested: run.papersIngested,
    papersAfterDedup: run.papersAfterDedup,
    papersCoarsePassed: run.papersCoarsePassed,
    papersFulltextRetrieved: run.papersFulltextRetrieved,
    papersMethodsAnalysed: run.papersMethodsAnalysed,
    papersEnriched: run.papersEnriched,
    papersAdjudicated: run.papersAdjudicated,
    totalCostUsd: run.totalCostUsd,
    errors: run.errors,
  });
}
