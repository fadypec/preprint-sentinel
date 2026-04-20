"use client";

import { memo, useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  Legend,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { riskStyle } from "@/lib/risk-colors";

/** Shared dark-mode tooltip style for all Recharts charts */
const tooltipStyle = {
  contentStyle: { backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0" },
  itemStyle: { color: "#e2e8f0" },
  labelStyle: { color: "#94a3b8" },
};

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
type TierWeek = { week: string; critical: number; high: number; medium: number; low: number };
type DimensionTrendWeek = {
  week: string;
  [key: string]: string | number;
};
type VolumeDay = { day: string; count: number };

type Props = {
  countryData: RateRow[];
  institutionData: RateRow[];
  emergingCategories: EmergingRow[];
  highScorePapers: HighScorePaper[];
  tierOverTime: TierWeek[];
  dimensionTrends: DimensionTrendWeek[];
  volumePerDay: VolumeDay[];
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
    <div role="group" aria-label="Chart view mode" className="inline-flex rounded-md border border-slate-200 text-[10px] dark:border-slate-700">
      <button
        onClick={() => onChange("count")}
        aria-pressed={value === "count"}
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
        aria-pressed={value === "rate"}
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

// Colors for dimension trend lines
const DIMENSION_COLORS: Record<string, string> = {
  pathogen_enhancement: "#ef4444",
  synthesis_barrier_lowering: "#f97316",
  select_agent_relevance: "#eab308",
  novel_technique: "#3b82f6",
  information_hazard: "#8b5cf6",
  defensive_framing: "#06b6d4",
};

export const AnalyticsCharts = memo(function AnalyticsCharts({
  countryData,
  institutionData,
  emergingCategories,
  highScorePapers,
  tierOverTime,
  dimensionTrends,
  volumePerDay,
}: Props) {
  const { resolvedTheme } = useTheme();
  const textColor = resolvedTheme === "dark" ? "#94a3b8" : "#64748b";
  const gridColor = resolvedTheme === "dark" ? "#334155" : "#e2e8f0";

  const [countryView, setCountryView] = useState<"count" | "rate">("rate");
  const [instView, setInstView] = useState<"count" | "rate">("rate");

  // Fetch OpenAlex per-country biomedical output for normalised flag rate
  const [countryBaseline, setCountryBaseline] = useState<Record<string, number>>({});
  useEffect(() => {
    fetch("/api/analytics/country-baseline")
      .then((r) => r.json())
      .then((d: Record<string, number>) => setCountryBaseline(d))
      .catch(() => {});
  }, []);

  // Country flag rate: flagged / OpenAlex total biomedical output
  const countryRateData = countryData
    .filter((r) => countryBaseline[r.name] && countryBaseline[r.name] > 0)
    .map((r) => ({
      name: r.name,
      value: Math.round((r.flagged / countryBaseline[r.name]) * 10000) / 100,
      label: `${r.flagged} flagged / ${countryBaseline[r.name].toLocaleString()} total`,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);

  const countryChartData = countryView === "rate" ? countryRateData : toCountData(countryData);
  const instChartData = instView === "rate" ? toRateData(institutionData) : toCountData(institutionData);

  // Pre-compute category rates and max for relative bar scaling
  const catRates = emergingCategories.map((cat) => {
    const recentRate = cat.recent_total > 0
      ? Math.round((cat.recent_flagged / cat.recent_total) * 1000) / 10
      : 0;
    const priorRate = cat.prior_total > 0
      ? Math.round((cat.prior_flagged / cat.prior_total) * 1000) / 10
      : 0;
    return { ...cat, recentRate, priorRate, change: Math.round((recentRate - priorRate) * 10) / 10 };
  })
  .sort((a, b) => b.recentRate - a.recentRate);
  const maxCatRate = Math.max(...catRates.map((c) => c.recentRate), 1);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Countries — with Count/Rate toggle */}
      <Card className="p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {countryView === "rate" ? "Country Flag Rate" : "Flagged Papers by Country"}
          </h2>
          <ViewToggle value={countryView} onChange={setCountryView} />
        </div>
        {countryChartData.length > 0 ? (
          <div role="img" aria-label="Bar chart showing flagged papers by country">
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
                {...tooltipStyle}
                formatter={(v, _name, item) => {
                  if (countryView === "rate") {
                    const payload = item?.payload as { label?: string } | undefined;
                    return [`${v}%`, payload?.label ?? "Flag rate"];
                  }
                  return [String(v), "Flagged"];
                }}
              />
              <Bar dataKey="value" fill="#06b6d4" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">
            {countryView === "rate" && Object.keys(countryBaseline).length === 0
              ? "Loading baseline data from OpenAlex..."
              : "No data yet."}
          </p>
        )}
        {countryView === "rate" && (
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            % of each country&apos;s total biomedical output (from OpenAlex) that we flagged as potential DURC.
          </p>
        )}
      </Card>

      {/* Institutions — with Count/Rate toggle */}
      <Card className="p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {instView === "rate" ? "Institution Flag Rate" : "Flagged Papers by Institution"}
          </h2>
          <ViewToggle value={instView} onChange={setInstView} />
        </div>
        {instChartData.length > 0 ? (
          <div role="img" aria-label="Bar chart showing top flagged institutions">
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
                {...tooltipStyle}
                formatter={(v) =>
                  instView === "rate" ? `${v}%` : String(v)
                }
              />
              <Bar dataKey="value" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
          </div>
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
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Category Trends (30d vs prior 30d)
        </h2>
        {catRates.length > 0 ? (
          <div className="space-y-2">
            {catRates.map((cat) => (
              <div key={cat.name} className="flex items-center gap-2 text-xs">
                <span className="w-28 truncate text-slate-700 dark:text-slate-300" title={cat.name}>
                  {cat.name}
                </span>
                <div className="flex-1">
                  <div
                    className="h-2 rounded-full bg-slate-200 dark:bg-slate-700"
                    role="meter"
                    aria-valuenow={cat.recentRate}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${cat.name} flag rate`}
                  >
                    <div
                      className="h-2 rounded-full bg-purple-500"
                      style={{ width: `${(cat.recentRate / maxCatRate) * 100}%` }}
                    />
                  </div>
                </div>
                <span className="w-14 text-right tabular-nums text-slate-600 dark:text-slate-400">
                  {cat.recentRate}%
                </span>
                <span
                  className={cn(
                    "w-14 text-right tabular-nums text-xs",
                    cat.change > 2 ? "font-medium text-red-500" : cat.change < -2 ? "text-green-500" : "text-slate-400",
                  )}
                >
                  {cat.change > 0 ? "+" : ""}{cat.change}pp
                </span>
              </div>
            ))}
            <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
              Flag rate by category (bar scaled to max, not 0–100%). Red = rising trend. &quot;pp&quot; = percentage point change.
            </p>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">Not enough data for trends yet.</p>
        )}
      </Card>

      {/* High-score papers this week */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Highest-Scoring Papers (Last 30 Days)
        </h2>
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
          <p className="py-8 text-center text-sm text-slate-500">No critical/high papers in the last 30 days.</p>
        )}
      </Card>

      {/* Papers processed per day (F-S7) */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Papers Processed Per Day (Last 30 Days)
        </h2>
        {volumePerDay.length > 0 ? (
          <div role="img" aria-label="Bar chart showing papers processed per day">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={volumePerDay}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="day" tick={{ fill: textColor, fontSize: 9 }} angle={-45} textAnchor="end" height={60} />
              <YAxis tick={{ fill: textColor, fontSize: 10 }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Papers" />
            </BarChart>
          </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">No data yet.</p>
        )}
      </Card>

      {/* Risk tier distribution over time (F-I3) */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Risk Tier Distribution Over Time
        </h2>
        {tierOverTime.length > 0 ? (
          <div role="img" aria-label="Stacked area chart showing risk tier distribution over time">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={tierOverTime}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="week" tick={{ fill: textColor, fontSize: 10 }} />
              <YAxis tick={{ fill: textColor, fontSize: 10 }} />
              <Tooltip {...tooltipStyle} />
              <Legend />
              <Area type="monotone" dataKey="critical" stackId="1" fill="#ef4444" stroke="#ef4444" name="Critical" />
              <Area type="monotone" dataKey="high" stackId="1" fill="#f97316" stroke="#f97316" name="High" />
              <Area type="monotone" dataKey="medium" stackId="1" fill="#eab308" stroke="#eab308" name="Medium" />
              <Area type="monotone" dataKey="low" stackId="1" fill="#22c55e" stroke="#22c55e" name="Low" />
            </AreaChart>
          </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">No data yet.</p>
        )}
      </Card>

      {/* Dimension trend lines (F-S5) */}
      <Card className="p-4 lg:col-span-2">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Average Dimension Scores Over Time
        </h2>
        {dimensionTrends.length > 0 ? (
          <div role="img" aria-label="Line chart showing average risk dimension scores over time">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={dimensionTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="week" tick={{ fill: textColor, fontSize: 10 }} />
              <YAxis tick={{ fill: textColor, fontSize: 10 }} domain={[0, 3]} />
              <Tooltip {...tooltipStyle} />
              <Legend />
              {Object.entries(DIMENSION_LABELS).map(([key, label]) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={DIMENSION_COLORS[key] ?? "#94a3b8"}
                  name={label}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">Not enough data for dimension trends yet.</p>
        )}
      </Card>
    </div>
  );
});
