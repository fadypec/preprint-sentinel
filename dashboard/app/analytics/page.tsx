import { prisma } from "@/lib/prisma";
import { KpiCard } from "@/components/kpi-card";
import { AnalyticsCharts } from "@/components/analytics-charts";
import { PaperCoverageHeatmap } from "@/components/paper-coverage-heatmap";
import { Card } from "@/components/ui/card";
import { PipelineStage } from "@prisma/client";

type DimensionTrendRow = {
  date: string;
  pathogen_enhancement: number;
  synthesis_barrier_lowering: number;
  select_agent_relevance: number;
  novel_technique: number;
  information_hazard: number;
  defensive_framing: number;
};

async function getDimensionTrends(
  since: Date,
): Promise<DimensionTrendRow[]> {
  return prisma.$queryRaw<DimensionTrendRow[]>`
    SELECT
      to_char(date_trunc('week', created_at), 'MM/DD') as date,
      ROUND(AVG((stage2_result->'dimensions'->'pathogen_enhancement'->>'score')::numeric), 1)::float as pathogen_enhancement,
      ROUND(AVG((stage2_result->'dimensions'->'synthesis_barrier_lowering'->>'score')::numeric), 1)::float as synthesis_barrier_lowering,
      ROUND(AVG((stage2_result->'dimensions'->'select_agent_relevance'->>'score')::numeric), 1)::float as select_agent_relevance,
      ROUND(AVG((stage2_result->'dimensions'->'novel_technique'->>'score')::numeric), 1)::float as novel_technique,
      ROUND(AVG((stage2_result->'dimensions'->'information_hazard'->>'score')::numeric), 1)::float as information_hazard,
      ROUND(AVG((stage2_result->'dimensions'->'defensive_framing'->>'score')::numeric), 1)::float as defensive_framing
    FROM papers
    WHERE created_at >= ${since}
      AND stage2_result IS NOT NULL
      AND stage2_result->'dimensions' IS NOT NULL
    GROUP BY date_trunc('week', created_at)
    ORDER BY date_trunc('week', created_at)
  `;
}

async function getStats() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const papersToday = await prisma.paper.count({
    where: {
      createdAt: { gte: today },
      pipelineStage: { not: PipelineStage.ingested },
    },
  });

  const criticalHighToday = await prisma.paper.count({
    where: {
      createdAt: { gte: today },
      riskTier: { in: ["critical", "high"] },
    },
  });

  const papersLastWeek = await prisma.paper.count({
    where: {
      createdAt: { gte: sevenDaysAgo },
      pipelineStage: { not: PipelineStage.ingested },
    },
  });
  const dailyAvg = Math.round(papersLastWeek / 7);

  const lastRun = await prisma.pipelineRun.findFirst({
    orderBy: { startedAt: "desc" },
  });

  const papersOverTime = await prisma.$queryRaw<
    {
      date: string;
      critical: number;
      high: number;
      medium: number;
      low: number;
    }[]
  >`
    SELECT
      to_char(created_at::date, 'MM/DD') as date,
      COUNT(*) FILTER (WHERE risk_tier = 'critical')::int as critical,
      COUNT(*) FILTER (WHERE risk_tier = 'high')::int as high,
      COUNT(*) FILTER (WHERE risk_tier = 'medium')::int as medium,
      COUNT(*) FILTER (WHERE risk_tier = 'low')::int as low
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND pipeline_stage != 'ingested'
    GROUP BY created_at::date
    ORDER BY created_at::date
  `;

  const topInstitutions = await prisma.$queryRaw<
    { name: string; count: number }[]
  >`
    SELECT corresponding_institution as name, COUNT(*)::int as count
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND risk_tier IN ('critical', 'high')
      AND corresponding_institution IS NOT NULL
    GROUP BY corresponding_institution
    ORDER BY count DESC
    LIMIT 10
  `;

  const topCategories = await prisma.$queryRaw<
    { name: string; count: number }[]
  >`
    SELECT subject_category as name, COUNT(*)::int as count
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND pipeline_stage != 'ingested'
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
    WHERE created_at >= ${thirtyDaysAgo}
      AND pipeline_stage != 'ingested'
      AND enrichment_data->'openalex'->>'primary_institution_country' IS NOT NULL
    GROUP BY enrichment_data->'openalex'->>'primary_institution_country'
    ORDER BY count DESC
    LIMIT 10
  `;

  return {
    papersToday,
    criticalHighToday,
    dailyAvg,
    trendPct:
      dailyAvg > 0
        ? Math.round(((papersToday - dailyAvg) / dailyAvg) * 100)
        : 0,
    lastRunOk: lastRun
      ? !(Array.isArray(lastRun.errors) && lastRun.errors.length > 0)
      : null,
    papersOverTime,
    topInstitutions,
    topCategories,
    topCountries,
    dimensionTrends: await getDimensionTrends(thirtyDaysAgo),
  };
}

export default async function AnalyticsPage() {
  const stats = await getStats();

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Analytics
      </h1>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Papers Today"
          value={stats.papersToday}
          trend={stats.trendPct}
          subtitle={`7-day avg: ${stats.dailyAvg}`}
        />
        <KpiCard
          title="Critical/High Today"
          value={stats.criticalHighToday}
        />
        <KpiCard title="Daily Average (7d)" value={stats.dailyAvg} />
        <KpiCard
          title="Pipeline Health"
          value={
            stats.lastRunOk === null
              ? "No runs"
              : stats.lastRunOk
                ? "Healthy"
                : "Error"
          }
        />
      </div>

      <Card className="mb-6 p-4">
        <PaperCoverageHeatmap />
      </Card>

      <AnalyticsCharts
        papersOverTime={stats.papersOverTime}
        topInstitutions={stats.topInstitutions}
        topCategories={stats.topCategories}
        topCountries={stats.topCountries}
        dimensionTrends={stats.dimensionTrends}
      />
    </div>
  );
}
