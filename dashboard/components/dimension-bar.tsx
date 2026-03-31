import { cn } from "@/lib/utils";
import { dimensionColor } from "@/lib/risk-colors";

type DimensionBarProps = {
  label: string;
  score: number;
  maxScore?: number;
  justification?: string;
};

export function DimensionBar({ label, score, maxScore = 3, justification }: DimensionBarProps) {
  const pct = (score / maxScore) * 100;
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-600 dark:text-slate-400">{label}</span>
        <span className="font-semibold text-slate-700 dark:text-slate-300">
          {score}/{maxScore}
        </span>
      </div>
      <div
        className="mt-1 h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-600"
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={maxScore}
        aria-label={`${label}: ${score} out of ${maxScore}`}
      >
        <div
          className={cn("h-full rounded-full transition-all", dimensionColor(score))}
          style={{ width: `${pct}%` }}
        />
      </div>
      {justification && (
        <p className="mt-1 text-[10px] leading-tight text-slate-500 dark:text-slate-400">
          {justification}
        </p>
      )}
    </div>
  );
}
