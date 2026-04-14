"use client";

import { memo, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { riskStyle } from "@/lib/risk-colors";

type RateRow = { name: string; flagged: number; total: number };
type EmergingRow = {
  name: string;
  recent_flagged: number;
  recent_total: number;
  prior_flagged: number;
  prior_total: number;
};
type HighScorePaper = {
  id: string;
  title: string;
  risk_tier: string;
  aggregate_score: number | null;
  top_dimension: string;
  posted_date: string;
};

type Props = {
  countryData: RateRow[];
  institutionData: RateRow[];
  emergingCategories: EmergingRow[];
  highScorePapers: HighScorePaper[];
};

/** Small toggle for switching between Count and Rate views */
function ViewToggle({
  value,
  onChange,
}: {
  value: "count" | "rate";
  onChange: (v: "count" | "rate") => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-slate-200 text-[10px] dark:border-slate-700">
      <button
        onClick={() => onChange("count")}
        className={cn(
          "rounded-l-md px-2 py-0.5 transition-colors",
          value === "count"
            ? "bg-slate-200 font-medium text-slate-900 dark:bg-slate-700 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-700 dark:text-slate-400",
        )}
      >
        Count
      </button>
      <button
        onClick={() => onChange("rate")}
        className={cn(
          "rounded-r-md px-2 py-0.5 transition-colors",
          value === "rate"
            ? "bg-slate-200 font-medium text-slate-900 dark:bg-slate-700 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-700 dark:text-slate-400",
        )}
      >
        Flag Rate
      </button>
    </div>
  );
}

/** Format rate data for the bar chart */
function toRateData(rows: RateRow[]) {
  return rows
    .map((r) => ({
      name: r.name,
      value: r.total > 0 ? Math.round((r.flagged / r.total) * 1000) / 10 : 0,
      label: `${r.flagged}/${r.total}`,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);
}

function toCountData(rows: RateRow[]) {
  return rows
    .map((r) => ({ name: r.name, value: r.flagged }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);
}

const DIMENSION_LABELS: Record<string, string> = {
  pathogen_enhancement: "Pathogen enhance.",
  synthesis_barrier_lowering: "Synthesis barriers",
  select_agent_relevance: "Select agent",
  novel_technique: "Novel technique",
  information_hazard: "Info hazard",
  defensive_framing: "Defensive framing",
};

export const AnalyticsCharts = memo(function AnalyticsCharts({
  countryData,
  institutionData,
  emergingCategories,
  highScorePapers,
}: Props) {
  const { resolvedTheme } = useTheme();
  const textColor = resolvedTheme === "dark" ? "#94a3b8" : "#64748b";
  const gridColor = resolvedTheme === "dark" ? "#334155" : "#e2e8f0";

  const [countryView, setCountryView] = useState<"count" | "rate">("rate");
  const [instView, setInstView] = useState<"count" | "rate">("rate");

  const countryChartData = countryView === "rate" ? toRateData(countryData) : toCountData(countryData);
  const instChartData = instView === "rate" ? toRateData(institutionData) : toCountData(institutionData);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Countries — with Count/Rate toggle */}
      <Card className="p-4">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {countryView === "rate" ? "Country Flag Rate" : "Flagged Papers by Country"}
          </h3>
          <ViewToggle value={countryView} onChange={setCountryView} />
        </div>
        {countryChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={countryChartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis
                type="number"
                tick={{ fill: textColor, fontSize: 10 }}
                unit={countryView === "rate" ? "%" : ""}
              />
              <YAxis type="category" dataKey="name" tick={{ fill: textColor, fontSize: 10 }} width={40} />
              <Tooltip
                formatter={(v) =>
                  countryView === "rate" ? `${v}%` : String(v)
                }
              />
              <Bar dataKey="value" fill="#06b6d4" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">No data yet.</p>
        )}
        {countryView === "rate" && (
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            % of papers from each country that were flagged. Min 5 papers.
          </p>
        )}
      </Card>

      {/* Institutions — with Count/Rate toggle */}
      <Card className="p-4">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {instView === "rate" ? "Institution Flag Rate" : "Flagged Papers by Institution"}
          </h3>
          <ViewToggle value={instView} onChange={setInstView} />
        </div>
        {instChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={instChartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis
                type="number"
                tick={{ fill: textColor, fontSize: 10 }}
                unit={instView === "rate" ? "%" : ""}
              />
              <YAxis type="category" dataKey="name" tick={{ fill: textColor, fontSize: 9 }} width={180} />
              <Tooltip
                formatter={(v) =>
                  instView === "rate" ? `${v}%` : String(v)
                }
              />
              <Bar dataKey="value" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">No data yet.</p>
        )}
        {instView === "rate" && (
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            % of papers from each institution that were flagged. Min 5 papers.
          </p>
        )}
      </Card>

      {/* Emerging categories — flag rate change */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Category Trends (30d vs prior 30d)
        </h3>
        {emergingCategories.length > 0 ? (
          <div className="space-y-2">
            {emergingCategories.map((cat) => {
              const recentRate = cat.recent_total > 0
                ? Math.round((cat.recent_flagged / cat.recent_total) * 100)
                : 0;
              const priorRate = cat.prior_total > 0
                ? Math.round((cat.prior_flagged / cat.prior_total) * 100)
                : 0;
              const change = recentRate - priorRate;
              return (
                <div key={cat.name} className="flex items-center gap-2 text-xs">
                  <span className="w-28 truncate text-slate-700 dark:text-slate-300" title={cat.name}>
                    {cat.name}
                  </span>
                  <div className="flex-1">
                    <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700">
                      <div
                        className="h-2 rounded-full bg-purple-500"
                        style={{ width: `${Math.min(recentRate, 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className="w-12 text-right tabular-nums text-slate-600 dark:text-slate-400">
                    {recentRate}%
                  </span>
                  <span
                    className={cn(
                      "w-12 text-right tabular-nums text-xs",
                      change > 5 ? "font-medium text-red-500" : change < -5 ? "text-green-500" : "text-slate-400",
                    )}
                  >
                    {change > 0 ? "+" : ""}{change}pp
                  </span>
                </div>
              );
            })}
            <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
              Flag rate by category. Red = increasing trend. &quot;pp&quot; = percentage points change.
            </p>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">Not enough data for trends yet.</p>
        )}
      </Card>

      {/* High-score papers this week */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Highest-Scoring Papers (Last 7 Days)
        </h3>
        {highScorePapers.length > 0 ? (
          <div className="space-y-2">
            {highScorePapers.map((paper) => {
              const style = riskStyle(paper.risk_tier as Parameters<typeof riskStyle>[0]);
              return (
                <a
                  key={paper.id}
                  href={`/paper/${paper.id}`}
                  className="block rounded-md border border-slate-200 p-2.5 text-xs no-underline transition-colors hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="line-clamp-1 font-medium text-slate-800 dark:text-slate-200">
                      {paper.title}
                    </span>
                    <Badge className={cn("shrink-0 text-[9px]", style.badge)}>
                      {paper.aggregate_score ?? "?"}/18
                    </Badge>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-500 dark:text-slate-400">
                    <span>{paper.posted_date}</span>
                    {paper.top_dimension && (
                      <>
                        <span>&middot;</span>
                        <span className="text-orange-600 dark:text-orange-400">
                          {DIMENSION_LABELS[paper.top_dimension] ?? paper.top_dimension}
                        </span>
                      </>
                    )}
                  </div>
                </a>
              );
            })}
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">No critical/high papers in the last 7 days.</p>
        )}
      </Card>
    </div>
  );
});
