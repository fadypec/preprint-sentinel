import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date coverage data for the heatmap.
 * Each date gets a status: "full" | "mesh" | "error" | null
 * based on pipeline runs that covered that date range.
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  // Fetch all completed runs with date ranges
  const runs = await prisma.$queryRaw<
    {
      from_date: string | null;
      to_date: string | null;
      pubmed_query_mode: string | null;
      errors: unknown;
      papers_ingested: number;
    }[]
  >`
    SELECT from_date, to_date, pubmed_query_mode, errors, papers_ingested
    FROM pipeline_runs
    WHERE finished_at IS NOT NULL
      AND from_date IS NOT NULL
      AND to_date IS NOT NULL
    ORDER BY started_at ASC
  `;

  // Build a date → status map
  // Later runs override earlier ones (last write wins)
  const coverage: Record<string, string> = {};

  for (const run of runs) {
    if (!run.from_date || !run.to_date) continue;

    const from = new Date(run.from_date);
    const to = new Date(run.to_date);
    const hasErrors =
      Array.isArray(run.errors) && run.errors.length > 0;

    let status: string;
    if (hasErrors && run.papers_ingested === 0) {
      status = "error";
    } else if (run.pubmed_query_mode === "all") {
      status = "full";
    } else {
      status = "mesh";
    }

    // Fill every date in the range
    const d = new Date(from);
    while (d <= to) {
      const key = d.toISOString().slice(0, 10);
      // Don't downgrade: full > mesh > error
      const existing = coverage[key];
      if (
        !existing ||
        status === "full" ||
        (status === "mesh" && existing === "error")
      ) {
        coverage[key] = status;
      }
      d.setDate(d.getDate() + 1);
    }
  }

  return Response.json(coverage);
}
