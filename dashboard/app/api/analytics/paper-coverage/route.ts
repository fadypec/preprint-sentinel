import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date, per-source paper counts AND which dates had pipeline runs.
 *
 * Response: {
 *   coverage: { "2026-04-08": { "biorxiv": 120, "pubmed": 45, ... }, ... },
 *   runDates: ["2026-04-08", "2026-04-09", ...]
 * }
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  // Per-date, per-source paper counts
  const rows = await prisma.$queryRaw<
    { posted_date: string; source_server: string; count: bigint }[]
  >`
    SELECT
      posted_date::text as posted_date,
      source_server::text as source_server,
      COUNT(*) as count
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND posted_date >= CURRENT_DATE - INTERVAL '200 days'
    GROUP BY posted_date, source_server
    ORDER BY posted_date, source_server
  `;

  const coverage: Record<string, Record<string, number>> = {};
  for (const row of rows) {
    if (!row.posted_date) continue;
    if (!coverage[row.posted_date]) coverage[row.posted_date] = {};
    coverage[row.posted_date][row.source_server] = Number(row.count);
  }

  // Dates that had at least one pipeline run (used to distinguish
  // "queried but zero results" from "not queried at all")
  const runRows = await prisma.$queryRaw<{ run_date: string }[]>`
    SELECT DISTINCT (started_at AT TIME ZONE 'UTC')::date::text as run_date
    FROM pipeline_runs
    WHERE started_at >= CURRENT_DATE - INTERVAL '200 days'
  `;
  const runDates = runRows.map((r) => r.run_date);

  return Response.json({ coverage, runDates });
}
