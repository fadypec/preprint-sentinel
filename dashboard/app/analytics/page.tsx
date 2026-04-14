import { prisma } from "@/lib/prisma";
import { KpiCard } from "@/components/kpi-card";
import nextDynamic from "next/dynamic";
import { PaperCoverageHeatmap } from "@/components/paper-coverage-heatmap";
import { Card } from "@/components/ui/card";

// Lazy-load recharts bundle (~400KB) — only fetched when analytics page is visited
const AnalyticsCharts = nextDynamic(
  () => import("@/components/analytics-charts").then((m) => m.AnalyticsCharts),
  { ssr: false, loading: () => <div className="h-80 animate-pulse rounded bg-slate-800/30" /> },
);

export const dynamic = "force-dynamic";

type DimensionTrendRow = {
  date: string;
  pathogen_enhancement: number;
  synthesis_barrier_lowering: number;
  select_agent_relevance: number;
  novel_technique: number;
  information_hazard: number;
  defensive_framing: number;
};

async function getDimensionTrends(since: Date): Promise<DimensionTrendRow[]> {
  // Weekly buckets (smooths daily noise), DD/MM format showing week start date
  return prisma.$queryRaw<DimensionTrendRow[]>`
    SELECT
      to_char(date_trunc('week', posted_date), 'DD/MM') as date,
      ROUND(AVG(
        (stage2_result->'dimensions'->'pathogen_enhancement'->>'score')::numeric
      ), 1)::float as pathogen_enhancement,
      ROUND(AVG(
        (stage2_result->'dimensions'->'synthesis_barrier_lowering'->>'score')::numeric
      ), 1)::float as synthesis_barrier_lowering,
      ROUND(AVG(
        (stage2_result->'dimensions'->'select_agent_relevance'->>'score')::numeric
      ), 1)::float as select_agent_relevance,
      ROUND(AVG(
        (stage2_result->'dimensions'->'novel_technique'->>'score')::numeric
      ), 1)::float as novel_technique,
      ROUND(AVG(
        (stage2_result->'dimensions'->'information_hazard'->>'score')::numeric
      ), 1)::float as information_hazard,
      ROUND(AVG(
        (stage2_result->'dimensions'->'defensive_framing'->>'score')::numeric
      ), 1)::float as defensive_framing
    FROM papers
    WHERE posted_date >= ${since}
      AND stage2_result IS NOT NULL
      AND stage2_result->'dimensions' IS NOT NULL
      AND is_duplicate_of IS NULL
    GROUP BY date_trunc('week', posted_date)
    ORDER BY date_trunc('week', posted_date)
  `;
}

async function getStats() {
  const sixtyDaysAgo = new Date();
  sixtyDaysAgo.setDate(sixtyDaysAgo.getDate() - 60);
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  // KPI 1: Unreviewed critical/high papers needing attention
  const unreviewedCritHigh = await prisma.paper.count({
    where: {
      riskTier: { in: ["critical", "high"] },
      reviewStatus: "unreviewed",
      isDuplicateOf: null,
    },
  });

  // KPI 2: Coverage gaps (weekdays with no papers in last 30d)
  // Computed client-side from coverage data, but we can get a server count too
  const coverageDays = await prisma.$queryRaw<{ day_count: bigint }[]>`
    SELECT COUNT(DISTINCT posted_date) as day_count
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND posted_date >= CURRENT_DATE - INTERVAL '30 days'
      AND EXTRACT(DOW FROM posted_date) BETWEEN 1 AND 5
  `;
  // 30 days × 5/7 ≈ 21-22 weekdays
  const weekdaysInRange = Math.round(30 * 5 / 7);
  const daysWithData = Number(coverageDays[0]?.day_count ?? 0);
  const coverageGaps = Math.max(0, weekdaysInRange - daysWithData);

  // KPI 3: False positive rate
  const reviewedPapers = await prisma.paper.count({
    where: {
      reviewStatus: { in: ["confirmed_concern", "false_positive"] },
    },
  });
  const fpCount = await prisma.paper.count({
    where: { reviewStatus: "false_positive" },
  });
  const fpRate = reviewedPapers > 0 ? Math.round((fpCount / reviewedPapers) * 100) : null;

  // Top institutions — extract university/institute name from long department strings
  // Uses regex to find the comma-segment containing University/Institut/College/etc,
  // falling back to the first segment if no keyword matches.
  const topInstitutions = await prisma.$queryRaw<
    { name: string; count: number }[]
  >`
    SELECT name, SUM(c)::int as count FROM (
      SELECT
        TRIM(COALESCE(
          SUBSTRING(
            COALESCE(
              enrichment_data->'openalex'->>'primary_institution',
              corresponding_institution
            )
            FROM '([^,]*(?:University|Institut|College|Hospital|Center|Centre|School|Academy)[^,]*)'
          ),
          SPLIT_PART(
            COALESCE(
              enrichment_data->'openalex'->>'primary_institution',
              corresponding_institution
            ), ',', 1
          )
        )) as name,
        COUNT(*)::int as c
      FROM papers
      WHERE is_duplicate_of IS NULL
        AND coarse_filter_passed = true
        AND COALESCE(
          enrichment_data->'openalex'->>'primary_institution',
          corresponding_institution
        ) IS NOT NULL
      GROUP BY name
    ) sub
    WHERE name != ''
    GROUP BY name
    ORDER BY count DESC
    LIMIT 10
  `;

  const topCategories = await prisma.$queryRaw<
    { name: string; count: number }[]
  >`
    SELECT subject_category as name, COUNT(*)::int as count
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND coarse_filter_passed = true
      AND subject_category IS NOT NULL
    GROUP BY subject_category
    ORDER BY count DESC
    LIMIT 10
  `;

  const topCountries = await prisma.$queryRaw<
    { name: string; count: number }[]
  >`
    SELECT
      enrichment_data->'openalex'->>'primary_institution_country' as name,
      COUNT(*)::int as count
    FROM papers
    WHERE is_duplicate_of IS NULL
      AND coarse_filter_passed = true
      AND enrichment_data->'openalex'->>'primary_institution_country' IS NOT NULL
    GROUP BY name
    ORDER BY count DESC
    LIMIT 10
  `;

  return {
    unreviewedCritHigh,
    coverageGaps,
    fpRate,
    reviewedPapers,
    topInstitutions,
    topCategories,
    topCountries,
    dimensionTrends: await getDimensionTrends(sixtyDaysAgo),
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
        topInstitutions={stats.topInstitutions}
        topCategories={stats.topCategories}
        topCountries={stats.topCountries}
        dimensionTrends={stats.dimensionTrends}
      />
    </div>
  );
}
