"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type DayData = { count: number; hasPubmed: boolean };
type Coverage = Record<string, DayData>;

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function isWeekday(dateStr: string): boolean {
  const day = new Date(dateStr + "T12:00:00").getDay();
  return day !== 0 && day !== 6;
}

/** Build array of date strings for last N days, newest first. */
function lastNDays(n: number): string[] {
  const days: string[] = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    days.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() - 1);
  }
  return days;
}

export function PaperCoverageHeatmap() {
  const [coverage, setCoverage] = useState<Coverage>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("/api/analytics/paper-coverage")
      .then((r) => r.json())
      .then((data) => {
        setCoverage(data);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const days = lastNDays(30);

  // Find gaps: weekdays with no papers in the last 30 days
  const gaps = days.filter((d) => isWeekday(d) && !coverage[d]);
  // Days with data but no PubMed
  const partialDays = days.filter(
    (d) => coverage[d] && !coverage[d].hasPubmed,
  );

  if (!loaded) {
    return (
      <div className="h-32 animate-pulse rounded bg-slate-800/30" />
    );
  }

  return (
    <div className="space-y-4">
      {/* Status summary */}
      {gaps.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-900/20 dark:text-green-300">
          <span className="text-lg">&#10003;</span>
          No gaps in the last 30 days. All weekdays have ingested papers.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
            <span className="text-lg">&#9888;</span>
            <span>
              <strong>{gaps.length} weekday{gaps.length !== 1 ? "s" : ""}</strong> with no
              ingested papers in the last 30 days:
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {gaps.map((d) => (
              <span
                key={d}
                className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300"
              >
                {formatDate(d)}
              </span>
            ))}
          </div>
        </div>
      )}

      {partialDays.length > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          <span className="text-lg">&#9888;</span>
          <span>
            <strong>{partialDays.length} day{partialDays.length !== 1 ? "s" : ""}</strong> with
            preprints only (no PubMed).
          </span>
        </div>
      )}

      {/* Recent days table */}
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-white dark:bg-slate-900">
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-700 dark:text-slate-400">
              <th className="py-1.5 font-medium">Date</th>
              <th className="py-1.5 font-medium text-right">Papers</th>
              <th className="py-1.5 font-medium text-right">Sources</th>
              <th className="py-1.5 font-medium text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => {
              const data = coverage[d];
              const weekday = isWeekday(d);
              const isGap = weekday && !data;
              return (
                <tr
                  key={d}
                  className={cn(
                    "border-b border-slate-100 dark:border-slate-800",
                    isGap && "bg-red-50/50 dark:bg-red-900/10",
                    !weekday && "text-slate-400 dark:text-slate-600",
                  )}
                >
                  <td className="py-1">{formatDate(d)}</td>
                  <td className="py-1 text-right tabular-nums">
                    {data ? data.count.toLocaleString() : "—"}
                  </td>
                  <td className="py-1 text-right">
                    {data
                      ? data.hasPubmed
                        ? "Preprints + PubMed"
                        : "Preprints only"
                      : "—"}
                  </td>
                  <td className="py-1 text-right">
                    {isGap ? (
                      <span className="font-medium text-red-600 dark:text-red-400">Gap</span>
                    ) : data ? (
                      <span className="text-green-600 dark:text-green-400">&#10003;</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
