import { Card } from "@/components/ui/card";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

type KpiCardProps = {
  title: string;
  value: string | number;
  trend?: number | null;
  subtitle?: string;
};

export function KpiCard({ title, value, trend, subtitle }: KpiCardProps) {
  const TrendIcon =
    trend && trend > 0
      ? TrendingUp
      : trend && trend < 0
        ? TrendingDown
        : Minus;
  const trendColor =
    trend && trend > 0
      ? "text-red-500"
      : trend && trend < 0
        ? "text-green-500"
        : "text-slate-400";

  return (
    <Card className="p-4" role="group" aria-label={`${title}: ${value}`}>
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
        {title}
      </p>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          {value}
        </span>
        {trend != null && (
          <span className={`flex items-center text-xs ${trendColor}`}>
            <TrendIcon className="mr-0.5 h-3 w-3" />
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      {subtitle && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {subtitle}
        </p>
      )}
    </Card>
  );
}
