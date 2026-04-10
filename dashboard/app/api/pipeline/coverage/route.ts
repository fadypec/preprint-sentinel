import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date pipeline run data for the coverage heatmap.
 *
 * Each date gets a status based on pipeline_runs:
 *   "success" — ran with no errors
 *   "error"   — ran but had errors
 *   (absent)  — no run on this date (gap in coverage)
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const rows = await prisma.$queryRaw<
    {
      run_date: string;
      runs: bigint;
      has_error: boolean;
      papers_ingested: bigint;
    }[]
  >`
    SELECT
      (started_at AT TIME ZONE 'UTC')::date::text as run_date,
      COUNT(*) as runs,
      BOOL_OR(
        errors IS NOT NULL AND jsonb_array_length(errors) > 0
      ) as has_error,
      SUM(papers_ingested) as papers_ingested
    FROM pipeline_runs
    WHERE started_at >= CURRENT_DATE - INTERVAL '200 days'
    GROUP BY (started_at AT TIME ZONE 'UTC')::date
    ORDER BY run_date
  `;

  const coverage: Record<string, string> = {};

  for (const row of rows) {
    if (!row.run_date) continue;
    coverage[row.run_date] = row.has_error ? "error" : "success";
  }

  return Response.json(coverage);
}
