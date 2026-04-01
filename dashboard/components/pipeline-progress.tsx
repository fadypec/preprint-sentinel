"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCost } from "@/lib/utils";

type ProgressData = {
  running: boolean;
  id?: string;
  startedAt?: string;
  currentStage?: string | null;
  papersIngested?: number;
  papersAfterDedup?: number;
  papersCoarsePassed?: number;
  papersFulltextRetrieved?: number;
  papersMethodsAnalysed?: number;
  papersEnriched?: number;
  papersAdjudicated?: number;
  totalCostUsd?: number;
  errors?: string[] | null;
};

const STAGES = [
  { key: "ingest", label: "Ingest", stat: "papersIngested" },
  { key: "dedup", label: "Deduplicate", stat: "papersAfterDedup" },
  { key: "translation", label: "Translation", stat: null },
  { key: "coarse_filter", label: "Coarse Filter", stat: "papersCoarsePassed" },
  { key: "fulltext", label: "Full Text", stat: "papersFulltextRetrieved" },
  { key: "fulltext_translation", label: "Full-Text Translation", stat: null },
  { key: "methods_analysis", label: "Methods Analysis", stat: "papersMethodsAnalysed" },
  { key: "enrichment", label: "Enrichment", stat: "papersEnriched" },
  { key: "adjudication", label: "Adjudication", stat: "papersAdjudicated" },
] as const;

function stageIndex(stage: string | null | undefined): number {
  if (!stage) return -1;
  return STAGES.findIndex((s) => s.key === stage);
}

function elapsed(startedAt: string): string {
  const ms = Date.now() - new Date(startedAt).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

type Props = {
  initialRunning: boolean;
};

export function PipelineProgress({ initialRunning }: Props) {
  const [data, setData] = useState<ProgressData | null>(
    initialRunning ? { running: true } : null,
  );
  const [elapsedStr, setElapsedStr] = useState("");
  // Track whether we've ever seen the pipeline running in the API.
  // Prevents premature redirect when the Python process hasn't created
  // its DB row yet (race condition on first poll after trigger).
  const [everSawRunning, setEverSawRunning] = useState(false);

  useEffect(() => {
    if (!initialRunning && !data?.running) return;

    let active = true;

    async function poll() {
      try {
        const res = await fetch("/api/pipeline/progress");
        if (!res.ok) return;
        const json: ProgressData = await res.json();
        if (active) {
          if (json.running) {
            setEverSawRunning(true);
          }
          setData(json);
          if (!json.running && everSawRunning) {
            // Pipeline genuinely finished — reload page to show updated history
            window.location.href = "/pipeline";
          }
        }
      } catch {
        // ignore fetch errors
      }
    }

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [initialRunning, data?.running, everSawRunning]);

  // Elapsed timer
  useEffect(() => {
    if (!data?.startedAt || !data.running) return;
    const tick = () => setElapsedStr(elapsed(data.startedAt!));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [data?.startedAt, data?.running]);

  if (!data?.running) return null;

  const currentIdx = stageIndex(data.currentStage);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Pipeline running
          </span>
        </div>
        <span className="text-xs text-slate-400">{elapsedStr}</span>
      </div>

      <div className="space-y-1">
        {STAGES.map((stage, idx) => {
          const isComplete = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const statKey = stage.stat as keyof ProgressData | null;
          const statVal = statKey ? (data[statKey] as number) : null;

          return (
            <div key={stage.key} className="flex items-center gap-2">
              {isComplete ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              ) : isCurrent ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
              ) : (
                <Circle className="h-3.5 w-3.5 text-slate-300 dark:text-slate-600" />
              )}
              <span
                className={cn(
                  "text-xs",
                  isComplete && "text-slate-500 dark:text-slate-400",
                  isCurrent && "font-medium text-slate-700 dark:text-slate-200",
                  !isComplete && !isCurrent && "text-slate-400 dark:text-slate-600",
                )}
              >
                {stage.label}
              </span>
              {statVal != null && statVal > 0 && (
                <span className="text-[10px] text-slate-400">
                  ({statVal})
                </span>
              )}
            </div>
          );
        })}
      </div>

      {data.totalCostUsd != null && data.totalCostUsd > 0 && (
        <p className="text-[10px] text-slate-400">
          Cost so far: {formatCost(data.totalCostUsd)}
        </p>
      )}

      {Array.isArray(data.errors) && data.errors.length > 0 && (
        <div className="rounded bg-red-50 px-2 py-1.5 dark:bg-red-900/30">
          <p className="text-[10px] font-medium text-red-600 dark:text-red-400">
            {data.errors.length} error(s)
          </p>
          {data.errors.map((e, i) => (
            <p key={i} className="text-[10px] text-red-500 dark:text-red-400">
              {String(e)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
