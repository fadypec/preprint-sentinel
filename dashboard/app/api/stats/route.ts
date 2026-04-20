import { prisma } from "@/lib/prisma";
import { PipelineStage, RiskTier } from "@prisma/client";
import { apiRequireAuth } from "@/lib/auth-guard";

export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;
  try {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    // Run all independent queries in parallel
    const [papersToday, criticalHighToday, papersLastWeek, lastRun, institutionRows, categoryRows] =
      await Promise.all([
        prisma.paper.count({
          where: {
            createdAt: { gte: today },
            pipelineStage: { not: PipelineStage.ingested },
          },
        }),
        prisma.paper.count({
          where: {
            createdAt: { gte: today },
            riskTier: { in: [RiskTier.critical, RiskTier.high] },
          },
        }),
        prisma.paper.count({
          where: {
            createdAt: { gte: sevenDaysAgo },
            pipelineStage: { not: PipelineStage.ingested },
          },
        }),
        prisma.pipelineRun.findFirst({
          orderBy: { startedAt: "desc" },
        }),
        prisma.paper.groupBy({
          by: ["correspondingInstitution"],
          where: {
            createdAt: { gte: thirtyDaysAgo },
            riskTier: { in: [RiskTier.critical, RiskTier.high] },
            correspondingInstitution: { not: null },
          },
          _count: { id: true },
          orderBy: { _count: { id: "desc" } },
          take: 10,
        }),
        prisma.paper.groupBy({
          by: ["subjectCategory"],
          where: {
            createdAt: { gte: thirtyDaysAgo },
            pipelineStage: { not: PipelineStage.ingested },
            subjectCategory: { not: null },
          },
          _count: { id: true },
          orderBy: { _count: { id: "desc" } },
          take: 10,
        }),
      ]);

    const dailyAvg = Math.round(papersLastWeek / 7);

    const topInstitutions = institutionRows.map((r) => ({
      name: r.correspondingInstitution ?? "Unknown",
      count: r._count.id,
    }));

    const topCategories = categoryRows.map((r) => ({
      name: r.subjectCategory ?? "Unknown",
      count: r._count.id,
    }));

    const hasErrors = Array.isArray(lastRun?.errors) && lastRun.errors.length > 0;

    // Tier over time (last 30 days, bucketed by week)
    const tierOverTime = await prisma.$queryRaw<
      { week: string; critical: number; high: number; medium: number; low: number }[]
    >`
      SELECT
        DATE_TRUNC('week', posted_date)::date::text as week,
        COUNT(*) FILTER (WHERE risk_tier = 'critical')::int as critical,
        COUNT(*) FILTER (WHERE risk_tier = 'high')::int as high,
        COUNT(*) FILTER (WHERE risk_tier = 'medium')::int as medium,
        COUNT(*) FILTER (WHERE risk_tier = 'low')::int as low
      FROM papers
      WHERE is_duplicate_of IS NULL
        AND coarse_filter_passed = true
        AND posted_date >= ${thirtyDaysAgo}
        AND risk_tier IS NOT NULL
      GROUP BY DATE_TRUNC('week', posted_date)
      ORDER BY week ASC
    `;

    return Response.json({
      kpi: {
        papersToday,
        criticalHighToday,
        dailyAvg,
        trendPct:
          dailyAvg > 0
            ? Math.round(((papersToday - dailyAvg) / dailyAvg) * 100)
            : 0,
        lastRunStatus: lastRun ? (hasErrors ? "error" : "success") : "unknown",
      },
      topInstitutions,
      topCategories,
      tierOverTime,
    });
  } catch (err) {
    console.error("Stats API error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
