import { prisma } from "@/lib/prisma";
import { RunHistoryTable } from "@/components/run-history-table";
import { PipelineControls } from "@/components/pipeline-controls";
import { Card } from "@/components/ui/card";
import { triggerPipeline, cancelPipeline, togglePubmedQueryMode } from "./actions";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const [runs, settingsRow] = await Promise.all([
    prisma.pipelineRun.findMany({
      orderBy: { startedAt: "desc" },
      take: 50,
    }),
    prisma.pipelineSettings.findUnique({ where: { id: 1 } }),
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
            <RunHistoryTable runs={runs} />
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
              pubmedMode={pubmedMode}
              togglePubmedMode={togglePubmedQueryMode}
            />
          </Card>

        </div>
      </div>
    </div>
  );
}
