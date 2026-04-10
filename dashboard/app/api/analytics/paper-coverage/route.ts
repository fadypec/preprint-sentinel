import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date paper counts by posted_date for the intelligence
 * coverage heatmap. Shows how many non-duplicate papers we ingested
 * for each day that papers were posted on preprint servers.
 *
 * Response: { "2026-04-08": { count: 342, hasPubmed: true }, ... }
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const rows = await prisma.$queryRaw<
    {
      posted_date: string;
      total: bigint;
      has_pubmed: boolean;
    }[]
  >`
    SELECT
      posted_date::text as posted_date,
      COUNT(*) as total,
      BOOL_OR(source_server = 'pubmed') as has_pubmed
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND posted_date >= CURRENT_DATE - INTERVAL '200 days'
    GROUP BY posted_date
    ORDER BY posted_date
  `;

  const coverage: Record<string, { count: number; hasPubmed: boolean }> = {};

  for (const row of rows) {
    if (!row.posted_date) continue;
    coverage[row.posted_date] = {
      count: Number(row.total),
      hasPubmed: row.has_pubmed,
    };
  }

  return Response.json(coverage);
}
