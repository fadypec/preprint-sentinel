import { prisma } from "@/lib/prisma";
import { PipelineStage, RiskTier } from "@prisma/client";

export async function GET() {
  try {
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
        riskTier: { in: [RiskTier.critical, RiskTier.high] },
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

    const institutionRows = await prisma.paper.groupBy({
      by: ["correspondingInstitution"],
      where: {
        createdAt: { gte: thirtyDaysAgo },
        riskTier: { in: [RiskTier.critical, RiskTier.high] },
        correspondingInstitution: { not: null },
      },
      _count: { id: true },
      orderBy: { _count: { id: "desc" } },
      take: 10,
    });

    const topInstitutions = institutionRows.map((r) => ({
      name: r.correspondingInstitution ?? "Unknown",
      count: r._count.id,
    }));

    const categoryRows = await prisma.paper.groupBy({
      by: ["subjectCategory"],
      where: {
        createdAt: { gte: thirtyDaysAgo },
        pipelineStage: { not: PipelineStage.ingested },
        subjectCategory: { not: null },
      },
      _count: { id: true },
      orderBy: { _count: { id: "desc" } },
      take: 10,
    });

    const topCategories = categoryRows.map((r) => ({
      name: r.subjectCategory ?? "Unknown",
      count: r._count.id,
    }));

    const hasErrors = Array.isArray(lastRun?.errors) && lastRun.errors.length > 0;

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
    });
  } catch (err) {
    console.error("Stats API error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
