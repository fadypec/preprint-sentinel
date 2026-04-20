import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  ArrowRight,
  AlertTriangle,
  CircleCheck,
  CircleMinus,
} from "lucide-react";

type StageInfo = {
  key: string;
  label: string;
  count: number;
  sub?: { label: string; count: number; variant?: "default" | "destructive" | "outline" | "warning" }[];
};

export type BacklogData = {
  stages: StageInfo[];
  total: number;
};

export function PipelineBacklog({ data }: { data: BacklogData }) {
  const maxCount = Math.max(...data.stages.map((s) => s.count), 1);

  return (
    <div className="space-y-1">
      {data.stages.map((stage, i) => {
        const pct = Math.max((stage.count / maxCount) * 100, 2);
        const hasIssues = stage.sub?.some((s) => s.variant === "destructive" || s.variant === "warning");
        const allDone = stage.count === 0 && i < data.stages.length - 1;

        return (
          <div key={stage.key}>
            {i > 0 && (
              <div className="flex justify-center py-0.5">
                <ArrowRight className="h-3 w-3 -rotate-90 text-slate-300 dark:text-slate-600" aria-hidden="true" />
              </div>
            )}
            <div className="group rounded-md border border-slate-200 px-3 py-2.5 dark:border-slate-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {hasIssues ? (
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
                  ) : allDone ? (
                    <CircleCheck className="h-3.5 w-3.5 text-green-500" aria-hidden="true" />
                  ) : (
                    <CircleMinus className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
                  )}
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    {stage.label}
                  </span>
                </div>
                <span
                  className={cn(
                    "font-mono text-sm font-semibold",
                    stage.count > 0
                      ? "text-slate-900 dark:text-slate-100"
                      : "text-slate-500 dark:text-slate-500"
                  )}
                >
                  {stage.count.toLocaleString()}
                </span>
              </div>

              {/* Bar */}
              <div
                className="mt-1.5 h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800"
                role="meter"
                aria-valuenow={stage.count}
                aria-valuemin={0}
                aria-valuemax={data.total}
                aria-label={`${stage.label} backlog`}
              >
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    hasIssues
                      ? "bg-amber-500/80"
                      : stage.count > 0
                        ? "bg-blue-500/70"
                        : "bg-slate-200 dark:bg-slate-700"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>

              {/* Sub-breakdowns */}
              {stage.sub && stage.sub.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                  {stage.sub.map((s) => (
                    <span
                      key={s.label}
                      className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400"
                    >
                      {s.label}:
                      <Badge
                        variant={s.variant ?? "outline"}
                        className="text-[10px] px-1.5 py-0"
                      >
                        {s.count.toLocaleString()}
                      </Badge>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}

      <div className="pt-1 text-center text-[11px] text-slate-500 dark:text-slate-500">
        {data.total.toLocaleString()} total non-duplicate papers
      </div>
    </div>
  );
}
