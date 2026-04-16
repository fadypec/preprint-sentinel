import { prisma } from "@/lib/prisma";
import { RunHistoryTable } from "@/components/run-history-table";
import { PipelineControls } from "@/components/pipeline-controls";
import { CoverageHeatmap } from "@/components/coverage-heatmap";
import { PipelineBacklog, type BacklogData } from "@/components/pipeline-backlog";
import { Card } from "@/components/ui/card";
import { triggerPipeline, cancelPipeline, clearRunHistory, togglePubmedQueryMode, reprocessErrors } from "./actions";

type StageCount = { pipeline_stage: string; coarse_filter_passed: boolean | null; risk_tier: string | null; count: bigint };

async function getBacklogData(): Promise<BacklogData> {
  const rows = await prisma.$queryRaw<StageCount[]>`
    SELECT pipeline_stage, coarse_filter_passed, risk_tier, COUNT(*) as count
    FROM papers
    WHERE is_duplicate_of IS NULL
    GROUP BY pipeline_stage, coarse_filter_passed, risk_tier
    ORDER BY pipeline_stage
  `;

  const counts: Record<string, Record<string, number>> = {};
  let total = 0;
  for (const r of rows) {
    const key = r.pipeline_stage;
    const subKey = r.coarse_filter_passed === null ? "pending" : r.coarse_filter_passed ? "passed" : "filtered";
    const tierKey = r.risk_tier ?? "none";
    const n = Number(r.count);
    total += n;
    if (!counts[key]) counts[key] = {};
    counts[key][`${subKey}:${tierKey}`] = (counts[key][`${subKey}:${tierKey}`] ?? 0) + n;
    counts[key]["_total"] = (counts[key]["_total"] ?? 0) + n;
  }

  const ingested = counts["ingested"]?.["_total"] ?? 0;
  const cfPassed = Object.entries(counts["coarse_filtered"] ?? {})
    .filter(([k]) => k.startsWith("passed:"))
    .reduce((s, [, v]) => s + v, 0);
  const cfFiltered = Object.entries(counts["coarse_filtered"] ?? {})
    .filter(([k]) => k.startsWith("filtered:"))
    .reduce((s, [, v]) => s + v, 0);
  const ftTotal = counts["fulltext_retrieved"]?.["_total"] ?? 0;
  const maTotal = counts["methods_analysed"]?.["_total"] ?? 0;

  const adjByTier: Record<string, number> = {};
  for (const [k, v] of Object.entries(counts["adjudicated"] ?? {})) {
    if (k === "_total") continue;
    const tier = k.split(":")[1];
    adjByTier[tier] = (adjByTier[tier] ?? 0) + v;
  }
  const adjTotal = counts["adjudicated"]?.["_total"] ?? 0;

  return {
    total,
    stages: [
      {
        key: "ingested",
        label: "Awaiting Coarse Filter",
        count: ingested,
        sub: ingested > 0 ? [{ label: "Needs processing", count: ingested, variant: "warning" as const }] : [],
      },
      {
        key: "coarse_filtered",
        label: "Coarse Filtered",
        count: cfPassed + cfFiltered,
        sub: [
          { label: "Passed", count: cfPassed, variant: "default" as const },
          { label: "Filtered out", count: cfFiltered, variant: "outline" as const },
        ],
      },
      {
        key: "fulltext_retrieved",
        label: "Awaiting Methods Analysis",
        count: ftTotal,
        sub: ftTotal > 0 ? [{ label: "Stuck / pending", count: ftTotal, variant: "warning" as const }] : [],
      },
      {
        key: "methods_analysed",
        label: "Awaiting Adjudication",
        count: maTotal,
        sub: maTotal > 0 ? [{ label: "Pending", count: maTotal, variant: "outline" as const }] : [],
      },
      {
        key: "adjudicated",
        label: "Adjudicated",
        count: adjTotal,
        sub: [
          ...(adjByTier["critical"] ? [{ label: "Critical", count: adjByTier["critical"], variant: "destructive" as const }] : []),
          ...(adjByTier["high"] ? [{ label: "High", count: adjByTier["high"], variant: "destructive" as const }] : []),
          ...(adjByTier["medium"] ? [{ label: "Medium", count: adjByTier["medium"], variant: "warning" as const }] : []),
          ...(adjByTier["low"] ? [{ label: "Low", count: adjByTier["low"], variant: "outline" as const }] : []),
          ...(adjByTier["none"] ? [{ label: "No tier", count: adjByTier["none"], variant: "destructive" as const }] : []),
        ],
      },
    ],
  };
}

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  // Admin only — redirects non-admin users to home
  const { requireAdmin } = await import("@/lib/auth-guard");
  await requireAdmin();

  const [runs, settingsRow, backlog] = await Promise.all([
    prisma.pipelineRun.findMany({
      orderBy: { startedAt: "desc" },
      take: 50,
    }),
    prisma.pipelineSettings.findUnique({ where: { id: 1 } }),
    getBacklogData(),
  ]);

  const dashSettings = (settingsRow?.settings as Record<string, unknown>) ?? {};
  const pubmedMode =
    typeof dashSettings.pubmed_query_mode === "string"
      ? dashSettings.pubmed_query_mode
      : "mesh_filtered";

  // Derive status from DB — no sidecar needed
  const runningRun = runs.find((r) => r.finishedAt === null);
  const pipelineStatus = {
    running: !!runningRun,
    paused: false,
  };

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Pipeline
      </h1>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="p-4">
            <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Run History
            </h2>
            <RunHistoryTable runs={runs} clearAction={clearRunHistory} />
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-4">
            <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Controls
            </h2>
            <PipelineControls
              initialStatus={pipelineStatus}
              triggerAction={triggerPipeline}
              cancelAction={cancelPipeline}
              reprocessAction={reprocessErrors}
              pubmedMode={pubmedMode}
              togglePubmedMode={togglePubmedQueryMode}
            />
          </Card>

          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Paper Backlog
            </h2>
            <PipelineBacklog data={backlog} />
          </Card>

          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Pipeline Runs
            </h2>
            <CoverageHeatmap />
          </Card>
        </div>
      </div>
    </div>
  );
}
