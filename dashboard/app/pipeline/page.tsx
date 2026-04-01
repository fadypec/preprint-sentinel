import { prisma } from "@/lib/prisma";
import { RunHistoryTable } from "@/components/run-history-table";
import { PipelineControls } from "@/components/pipeline-controls";
import { Card } from "@/components/ui/card";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const runs = await prisma.pipelineRun.findMany({
    orderBy: { startedAt: "desc" },
    take: 50,
  });

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

        <div>
          <Card className="p-4">
            <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Controls
            </h2>
            <PipelineControls initialStatus={pipelineStatus} />
          </Card>
        </div>
      </div>
    </div>
  );
}
