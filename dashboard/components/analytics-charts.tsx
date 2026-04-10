"use client";

import { memo } from "react";
import {
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
  topInstitutions: InstitutionData;
  topCategories: InstitutionData;
  topCountries: InstitutionData;
  dimensionTrends: DimensionTrendData;
};

export const AnalyticsCharts = memo(function AnalyticsCharts({
  topInstitutions,
  topCategories,
  topCountries,
  dimensionTrends,
}: Props) {
  const { resolvedTheme } = useTheme();
  const textColor = resolvedTheme === "dark" ? "#94a3b8" : "#64748b";
  const gridColor = resolvedTheme === "dark" ? "#334155" : "#e2e8f0";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Top flagged institutions — horizontal bar */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Institutions
        </h3>
        {topInstitutions.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={topInstitutions} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis type="number" tick={{ fill: textColor, fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: textColor, fontSize: 10 }}
                width={150}
              />
              <Tooltip />
              <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No institution data available yet.
          </p>
        )}
      </Card>

      {/* Top flagged categories — horizontal bar */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Categories
        </h3>
        {topCategories.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={topCategories} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis type="number" tick={{ fill: textColor, fontSize: 10 }} />
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
        ) : (
          <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No category data available yet.
          </p>
        )}
      </Card>

      {/* Top countries — horizontal bar */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Countries
        </h3>
        {topCountries.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={topCountries} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis type="number" tick={{ fill: textColor, fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: textColor, fontSize: 10 }}
                width={40}
              />
              <Tooltip />
              <Bar dataKey="count" fill="#06b6d4" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No country data available yet.
          </p>
        )}
      </Card>

      {/* Risk dimension trends — daily, DD/MM format */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Risk Dimension Trends (Daily Avg Score)
        </h3>
        {dimensionTrends.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={dimensionTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="date" tick={{ fill: textColor, fontSize: 10 }} />
              <YAxis domain={[0, 3]} tick={{ fill: textColor, fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="pathogen_enhancement" stroke={COLORS.critical} dot={false} name="Pathogen enhancement" />
              <Line type="monotone" dataKey="information_hazard" stroke={COLORS.high} dot={false} name="Information hazard" />
              <Line type="monotone" dataKey="synthesis_barrier_lowering" stroke={COLORS.medium} dot={false} name="Synthesis barriers" />
              <Line type="monotone" dataKey="novel_technique" stroke="#3b82f6" dot={false} name="Novel technique" />
              <Line type="monotone" dataKey="select_agent_relevance" stroke="#8b5cf6" dot={false} name="Select agent" />
              <Line type="monotone" dataKey="defensive_framing" stroke="#64748b" dot={false} name="Defensive framing" />
              <Legend />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            Not enough data for dimension trends yet.
          </p>
        )}
      </Card>
    </div>
  );
});
