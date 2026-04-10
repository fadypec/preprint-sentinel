"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

// { "2026-04-08": { "biorxiv": 120, "pubmed": 45, ... } }
type Coverage = Record<string, Record<string, number>>;

const ALL_SOURCES = [
  "biorxiv",
  "medrxiv",
  "europepmc",
  "pubmed",
  "arxiv",
  "research_square",
  "chemrxiv",
  "zenodo",
  "ssrn",
] as const;

const SOURCE_LABELS: Record<string, string> = {
  biorxiv: "bioRxiv",
  medrxiv: "medRxiv",
  europepmc: "EPMC",
  pubmed: "PubMed",
  arxiv: "arXiv",
  research_square: "ResSquare",
  chemrxiv: "ChemRxiv",
  zenodo: "Zenodo",
  ssrn: "SSRN",
};

const DAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function mondayIndex(jsDay: number): number {
  return (jsDay + 6) % 7;
}

function isWeekday(dateStr: string): boolean {
  const day = new Date(dateStr + "T12:00:00").getDay();
  return day !== 0 && day !== 6;
}

function formatDateShort(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

function sourceCount(day: Record<string, number> | undefined): number {
  if (!day) return 0;
  return Object.keys(day).length;
}

function totalPapers(day: Record<string, number> | undefined): number {
  if (!day) return 0;
  return Object.values(day).reduce((s, n) => s + n, 0);
}

function getHeatmapColor(sources: number): string {
  if (sources === 0) return "bg-slate-800 dark:bg-slate-700";
  if (sources <= 2) return "bg-green-300 dark:bg-green-800";
  if (sources <= 4) return "bg-green-500 dark:bg-green-600";
  return "bg-green-600 dark:bg-green-500";
}

function getHeatmapTitle(dateStr: string, day: Record<string, number> | undefined): string {
  if (!day || Object.keys(day).length === 0) {
    return `${formatDateShort(dateStr)}: No data`;
  }
  const total = totalPapers(day);
  const srcs = Object.keys(day).map((s) => SOURCE_LABELS[s] || s).join(", ");
  return `${formatDateShort(dateStr)}: ${total} papers from ${Object.keys(day).length} sources (${srcs})`;
}

function buildGrid(weeks: number) {
  const today = new Date();
  const endDay = new Date(today);
  const daysUntilSunday = (7 - mondayIndex(endDay.getDay()) - 1 + 7) % 7;
  endDay.setDate(endDay.getDate() + daysUntilSunday);

  const startDay = new Date(endDay);
  startDay.setDate(startDay.getDate() - (weeks * 7 - 1));
  startDay.setDate(startDay.getDate() - mondayIndex(startDay.getDay()));

  const grid: string[][] = [];
  const d = new Date(startDay);
  let currentWeek: string[] = [];

  while (d <= endDay) {
    if (currentWeek.length === 7) {
      grid.push(currentWeek);
      currentWeek = [];
    }
    currentWeek.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  if (currentWeek.length > 0) grid.push(currentWeek);
  return grid;
}

function monthLabels(grid: string[][]) {
  const labels: { label: string; col: number }[] = [];
  let lastMonth = -1;
  for (let w = 0; w < grid.length; w++) {
    const month = new Date(grid[w][0]).getMonth();
    if (month !== lastMonth) {
      labels.push({ label: MONTH_LABELS[month], col: w });
      lastMonth = month;
    }
  }
  return labels;
}

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
      .then((data: Coverage) => {
        setCoverage(data);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const WEEKS = 26;
  const grid = buildGrid(WEEKS);
  const months = monthLabels(grid);
  const today = new Date().toISOString().slice(0, 10);
  const last30 = lastNDays(30);

  // Find gaps
  const gaps = last30.filter((d) => isWeekday(d) && sourceCount(coverage[d]) === 0);

  // Show ALL configured sources so missing ones are visible as empty columns
  const orderedSources = ALL_SOURCES;

  if (!loaded) {
    return <div className="h-48 animate-pulse rounded bg-slate-800/30" />;
  }

  return (
    <div className="space-y-5">
      {/* Gap alert */}
      {gaps.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-900/20 dark:text-green-300">
          <span>&#10003;</span>
          No coverage gaps in the last 30 weekdays.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
            <span>&#9888;</span>
            <strong>{gaps.length}</strong>&nbsp;weekday{gaps.length !== 1 ? "s" : ""} with no
            ingested papers in the last 30 days.
          </div>
          <div className="flex flex-wrap gap-1.5">
            {gaps.map((d) => (
              <span
                key={d}
                className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300"
              >
                {formatDateShort(d)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 6-month heatmap — colour = number of sources */}
      <div>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          6-month overview — darker green = more sources contributing
        </p>
        <div className="flex" style={{ paddingLeft: 28 }}>
          {months.map(({ label, col }, i) => {
            const nextCol = i < months.length - 1 ? months[i + 1].col : grid.length;
            return (
              <span
                key={`${label}-${col}`}
                className="text-[10px] text-slate-500 dark:text-slate-400"
                style={{ width: (nextCol - col) * 13 }}
              >
                {label}
              </span>
            );
          })}
        </div>
        <div className="flex gap-[2px]">
          <div className="flex flex-col gap-[2px] pr-1">
            {DAY_LABELS.map((label, i) => (
              <div key={i} className="flex h-[11px] w-5 items-center justify-end">
                <span className="text-[9px] leading-none text-slate-500 dark:text-slate-400">
                  {label}
                </span>
              </div>
            ))}
          </div>
          {grid.map((week, wi) => (
            <div key={wi} className="flex flex-col gap-[2px]">
              {week.map((dateStr, di) => {
                const isFuture = dateStr > today;
                const day = coverage[dateStr];
                const srcs = sourceCount(day);
                return (
                  <div
                    key={dateStr}
                    className={cn(
                      "h-[11px] w-[11px] rounded-[2px]",
                      isFuture ? "bg-transparent" : getHeatmapColor(srcs),
                    )}
                    title={isFuture ? "" : getHeatmapTitle(dateStr, day)}
                    style={di >= 7 ? { display: "none" } : undefined}
                  />
                );
              })}
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-3">
          {[
            { color: "bg-slate-800 dark:bg-slate-700", label: "No data" },
            { color: "bg-green-300 dark:bg-green-800", label: "1\u20132 sources" },
            { color: "bg-green-500 dark:bg-green-600", label: "3\u20134 sources" },
            { color: "bg-green-600 dark:bg-green-500", label: "5+ sources" },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1">
              <div className={cn("h-[11px] w-[11px] rounded-[2px]", color)} />
              <span className="text-[10px] text-slate-500 dark:text-slate-400">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 30-day source detail table */}
      <div>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          Last 30 days — per-source breakdown
        </p>
        <div className="max-h-72 overflow-auto rounded border border-slate-200 dark:border-slate-700">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-white dark:bg-slate-900">
              <tr className="border-b border-slate-200 dark:border-slate-700">
                <th className="px-2 py-1.5 text-left font-medium text-slate-500 dark:text-slate-400">
                  Date
                </th>
                {orderedSources.map((src) => (
                  <th
                    key={src}
                    className="px-1.5 py-1.5 text-center font-medium text-slate-500 dark:text-slate-400"
                  >
                    {SOURCE_LABELS[src]}
                  </th>
                ))}
                <th className="px-2 py-1.5 text-right font-medium text-slate-500 dark:text-slate-400">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {last30.map((d) => {
                const day = coverage[d];
                const weekday = isWeekday(d);
                const isGap = weekday && sourceCount(day) === 0;
                return (
                  <tr
                    key={d}
                    className={cn(
                      "border-b border-slate-100 dark:border-slate-800",
                      isGap && "bg-red-50/50 dark:bg-red-900/10",
                      !weekday && "text-slate-400 dark:text-slate-600",
                    )}
                  >
                    <td className="whitespace-nowrap px-2 py-1">{formatDateShort(d)}</td>
                    {orderedSources.map((src) => {
                      const count = day?.[src];
                      return (
                        <td key={src} className="px-1.5 py-1 text-center tabular-nums">
                          {count ? (
                            <span className="text-green-600 dark:text-green-400">{count}</span>
                          ) : weekday ? (
                            <span className="text-slate-300 dark:text-slate-600">&mdash;</span>
                          ) : (
                            <span className="text-slate-300 dark:text-slate-700">&middot;</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-2 py-1 text-right tabular-nums font-medium">
                      {totalPapers(day) || (
                        <span className={isGap ? "text-red-500" : ""}>0</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
