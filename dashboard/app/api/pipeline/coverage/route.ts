import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Returns per-date coverage data for the heatmap.
 *
 * Derives coverage from the papers table (ground truth) rather than
 * pipeline_runs, so clearing run history doesn't destroy the heatmap.
 *
 * Each date gets a status based on which sources have papers:
 *   "full" — has PubMed papers (broader coverage)
 *   "mesh" — has papers but no PubMed (preprint servers only)
 */
export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  // Count papers per posted_date, split by whether PubMed is present
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

  const coverage: Record<string, string> = {};

  for (const row of rows) {
    if (!row.posted_date) continue;
    const key = row.posted_date;
    coverage[key] = row.has_pubmed ? "full" : "mesh";
  }

  return Response.json(coverage);
}
