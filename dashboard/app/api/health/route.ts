import { prisma } from "@/lib/prisma";

/**
 * Unauthenticated health check endpoint for infrastructure monitoring.
 *
 * Returns system status without requiring authentication so that load
 * balancers, container orchestrators, and uptime monitors can verify
 * the service is running. No sensitive data is exposed.
 *
 * GET /api/health
 */
export async function GET() {
  const now = new Date();
  let dbOk = false;
  let lastRunAt: string | null = null;
  let hoursSinceRun: number | null = null;
  let lastRunHadErrors = false;

  try {
    // Verify database connectivity with a lightweight query
    await prisma.$queryRaw`SELECT 1`;
    dbOk = true;

    // Check last pipeline run
    const lastRun = await prisma.pipelineRun.findFirst({
      orderBy: { startedAt: "desc" },
      select: {
        startedAt: true,
        finishedAt: true,
        errors: true,
      },
    });

    if (lastRun) {
      lastRunAt = lastRun.startedAt.toISOString();
      hoursSinceRun = Math.round(
        (now.getTime() - lastRun.startedAt.getTime()) / (1000 * 60 * 60),
      );
      lastRunHadErrors =
        Array.isArray(lastRun.errors) && lastRun.errors.length > 0;
    }
  } catch {
    // Database unreachable — dbOk stays false
  }

  // Determine overall status:
  // - "ok"       = DB reachable, pipeline ran within 48h, no errors
  // - "degraded" = DB reachable but pipeline is stale or had errors
  // - "error"    = DB unreachable
  let status: "ok" | "degraded" | "error" = "ok";
  if (!dbOk) {
    status = "error";
  } else if (
    hoursSinceRun === null ||
    hoursSinceRun > 48 ||
    lastRunHadErrors
  ) {
    status = "degraded";
  }

  const statusCode = status === "error" ? 503 : 200;

  return Response.json(
    {
      status,
      database: dbOk,
      last_pipeline_run: lastRunAt,
      hours_since_run: hoursSinceRun,
      last_run_had_errors: lastRunHadErrors,
      checked_at: now.toISOString(),
    },
    { status: statusCode },
  );
}
