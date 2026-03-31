"use client";

import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card } from "@/components/ui/card";
import { useTheme } from "next-themes";

const COLORS = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

type PapersOverTimeData = {
  date: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
}[];

type InstitutionData = { name: string; count: number }[];

type DimensionTrendData = {
  date: string;
  pathogen_enhancement: number;
  synthesis_barrier_lowering: number;
  select_agent_relevance: number;
  novel_technique: number;
  information_hazard: number;
  defensive_framing: number;
}[];

type Props = {
  papersOverTime: PapersOverTimeData;
  topInstitutions: InstitutionData;
  topCategories: InstitutionData;
  dimensionTrends: DimensionTrendData;
};

export function AnalyticsCharts({
  papersOverTime,
  topInstitutions,
  topCategories,
  dimensionTrends,
}: Props) {
  const { resolvedTheme } = useTheme();
  const textColor = resolvedTheme === "dark" ? "#94a3b8" : "#64748b";
  const gridColor = resolvedTheme === "dark" ? "#334155" : "#e2e8f0";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Papers over time — stacked area */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Papers Over Time
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={papersOverTime}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="date" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis tick={{ fill: textColor, fontSize: 10 }} />
            <Tooltip />
            <Area
              type="monotone"
              dataKey="critical"
              stackId="1"
              fill={COLORS.critical}
              stroke={COLORS.critical}
            />
            <Area
              type="monotone"
              dataKey="high"
              stackId="1"
              fill={COLORS.high}
              stroke={COLORS.high}
            />
            <Area
              type="monotone"
              dataKey="medium"
              stackId="1"
              fill={COLORS.medium}
              stroke={COLORS.medium}
            />
            <Area
              type="monotone"
              dataKey="low"
              stackId="1"
              fill={COLORS.low}
              stroke={COLORS.low}
            />
            <Legend />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Top flagged institutions — horizontal bar */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Institutions
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={topInstitutions} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis
              type="number"
              tick={{ fill: textColor, fontSize: 10 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: textColor, fontSize: 10 }}
              width={120}
            />
            <Tooltip />
            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Top flagged categories — horizontal bar */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Categories
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={topCategories} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis
              type="number"
              tick={{ fill: textColor, fontSize: 10 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: textColor, fontSize: 10 }}
              width={120}
            />
            <Tooltip />
            <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Risk dimension trends — line chart */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Risk Dimension Trends (Avg Score)
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={dimensionTrends}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="date" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis
              domain={[0, 3]}
              tick={{ fill: textColor, fontSize: 10 }}
            />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="pathogen_enhancement"
              stroke={COLORS.critical}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="information_hazard"
              stroke={COLORS.high}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="synthesis_barrier_lowering"
              stroke={COLORS.medium}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="novel_technique"
              stroke="#3b82f6"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="select_agent_relevance"
              stroke="#8b5cf6"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="defensive_framing"
              stroke="#64748b"
              dot={false}
            />
            <Legend />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
