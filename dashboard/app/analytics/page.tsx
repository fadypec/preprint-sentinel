import { prisma } from "@/lib/prisma";
import { KpiCard } from "@/components/kpi-card";
import { AnalyticsCharts } from "@/components/analytics-charts";
import { PaperCoverageHeatmap } from "@/components/paper-coverage-heatmap";
import { Card } from "@/components/ui/card";

export const dynamic = "force-dynamic";

async function getStats() {
  const sixtyDaysAgo = new Date();
  sixtyDaysAgo.setDate(sixtyDaysAgo.getDate() - 60);
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  // KPIs
  const unreviewedCritHigh = await prisma.paper.count({
    where: { riskTier: { in: ["critical", "high"] }, reviewStatus: "unreviewed", isDuplicateOf: null },
  });

  const coverageDays = await prisma.$queryRaw<[{ count: bigint }]>`
    SELECT COUNT(DISTINCT posted_date) as count FROM papers
    WHERE is_duplicate_of IS NULL AND posted_date >= CURRENT_DATE - INTERVAL '30 days'
      AND EXTRACT(DOW FROM posted_date) BETWEEN 1 AND 5
  `;
  const weekdaysInRange = Math.round(30 * 5 / 7);
  const coverageGaps = Math.max(0, weekdaysInRange - Number(coverageDays[0]?.count ?? 0));

  const reviewedPapers = await prisma.paper.count({
    where: { reviewStatus: { in: ["confirmed_concern", "false_positive"] } },
  });
  const fpCount = await prisma.paper.count({ where: { reviewStatus: "false_positive" } });
  const fpRate = reviewedPapers > 0 ? Math.round((fpCount / reviewedPapers) * 100) : null;

  // --- Countries: raw count + flag rate ---
  const countryData = await prisma.$queryRaw<
    { name: string; flagged: number; total: number }[]
  >`
    SELECT
      enrichment_data->'openalex'->>'primary_institution_country' as name,
      COUNT(*) FILTER (WHERE coarse_filter_passed = true)::int as flagged,
      COUNT(*)::int as total
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND enrichment_data->'openalex'->>'primary_institution_country' IS NOT NULL
    GROUP BY name
    HAVING COUNT(*) >= 5
    ORDER BY COUNT(*) FILTER (WHERE coarse_filter_passed = true) DESC
    LIMIT 15
  `;

  // --- Institutions: raw count + flag rate ---
  const institutionData = await prisma.$queryRaw<
    { name: string; flagged: number; total: number }[]
  >`
    SELECT name, SUM(flagged)::int as flagged, SUM(total)::int as total FROM (
      SELECT
        TRIM(COALESCE(
          SUBSTRING(
            COALESCE(enrichment_data->'openalex'->>'primary_institution', corresponding_institution)
            FROM '([^,]*(?:University|Institut|College|Hospital|Center|Centre|School|Academy)[^,]*)'
          ),
          SPLIT_PART(
            COALESCE(enrichment_data->'openalex'->>'primary_institution', corresponding_institution),
            ',', 1
          )
        )) as name,
        COUNT(*) FILTER (WHERE coarse_filter_passed = true)::int as flagged,
        COUNT(*)::int as total
      FROM papers
      WHERE is_duplicate_of IS NULL
        AND COALESCE(enrichment_data->'openalex'->>'primary_institution', corresponding_institution) IS NOT NULL
      GROUP BY name
    ) sub
    WHERE name != '' AND total >= 5
    GROUP BY name
    ORDER BY flagged DESC
    LIMIT 15
  `;

  // --- Emerging categories: flag rate change (last 30d vs prior 30d) ---
  const emergingCategories = await prisma.$queryRaw<
    { name: string; recent_flagged: number; recent_total: number; prior_flagged: number; prior_total: number }[]
  >`
    SELECT
      subject_category as name,
      COUNT(*) FILTER (WHERE posted_date >= ${thirtyDaysAgo} AND coarse_filter_passed = true)::int as recent_flagged,
      COUNT(*) FILTER (WHERE posted_date >= ${thirtyDaysAgo})::int as recent_total,
      COUNT(*) FILTER (WHERE posted_date < ${thirtyDaysAgo} AND coarse_filter_passed = true)::int as prior_flagged,
      COUNT(*) FILTER (WHERE posted_date < ${thirtyDaysAgo})::int as prior_total
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND subject_category IS NOT NULL
      AND posted_date >= ${sixtyDaysAgo}
    GROUP BY subject_category
    HAVING COUNT(*) FILTER (WHERE posted_date >= ${thirtyDaysAgo}) >= 3
    ORDER BY COUNT(*) FILTER (WHERE posted_date >= ${thirtyDaysAgo} AND coarse_filter_passed = true) DESC
    LIMIT 10
  `;

  // --- High-score papers this week ---
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const highScorePapers = await prisma.$queryRaw<
    { id: string; title: string; risk_tier: string; aggregate_score: number | null; top_dimension: string; posted_date: string }[]
  >`
    SELECT
      id::text,
      title,
      risk_tier::text,
      aggregate_score,
      (
        SELECT key FROM jsonb_each_text(stage2_result->'dimensions')
        WHERE key IN ('pathogen_enhancement','synthesis_barrier_lowering','select_agent_relevance','novel_technique','information_hazard','defensive_framing')
        ORDER BY (value::jsonb->>'score')::int DESC NULLS LAST
        LIMIT 1
      ) as top_dimension,
      posted_date::text
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND coarse_filter_passed = true
      AND risk_tier IN ('critical', 'high')
      AND posted_date >= ${sevenDaysAgo}
      AND stage2_result IS NOT NULL
    ORDER BY
      CASE risk_tier WHEN 'critical' THEN 2 WHEN 'high' THEN 1 ELSE 0 END DESC,
      COALESCE(aggregate_score, 0) DESC
    LIMIT 10
  `;

  return {
    unreviewedCritHigh,
    coverageGaps,
    fpRate,
    reviewedPapers,
    countryData,
    institutionData,
    emergingCategories,
    highScorePapers,
  };
}

export default async function AnalyticsPage() {
  const stats = await getStats();

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Analytics
      </h1>

      {/* KPIs */}
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <KpiCard
          title="Unreviewed Critical/High"
          value={stats.unreviewedCritHigh}
          subtitle={stats.unreviewedCritHigh > 0 ? "Needs analyst attention" : "All clear"}
        />
        <KpiCard
          title="Coverage Gaps (30d)"
          value={stats.coverageGaps}
          subtitle={stats.coverageGaps === 0 ? "No missing weekdays" : "Weekdays with no data"}
        />
        <KpiCard
          title="False Positive Rate"
          value={stats.fpRate !== null ? `${stats.fpRate}%` : "—"}
          subtitle={
            stats.reviewedPapers > 0
              ? `${stats.reviewedPapers} papers reviewed`
              : "No papers reviewed yet"
          }
        />
      </div>

      {/* Intelligence coverage */}
      <Card className="mb-6 p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Intelligence Coverage
        </h2>
        <PaperCoverageHeatmap />
      </Card>

      {/* Charts */}
      <AnalyticsCharts
        countryData={stats.countryData}
        institutionData={stats.institutionData}
        emergingCategories={stats.emergingCategories}
        highScorePapers={stats.highScorePapers}
      />
    </div>
  );
}
