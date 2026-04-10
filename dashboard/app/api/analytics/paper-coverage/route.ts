import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date, per-source paper counts for the intelligence
 * coverage heatmap and detail table.
 *
 * Response: { "2026-04-08": { "biorxiv": 120, "pubmed": 45, ... }, ... }
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const rows = await prisma.$queryRaw<
    {
      posted_date: string;
      source_server: string;
      count: bigint;
    }[]
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

  return Response.json(coverage);
}
