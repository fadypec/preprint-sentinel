"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Coverage = Record<string, string>; // date string → "full" | "mesh" | "error"

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];
const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function getCellColor(status: string | undefined): string {
  switch (status) {
    case "full":
      return "bg-green-500";
    case "mesh":
      return "bg-amber-500";
    case "error":
      return "bg-red-500";
    default:
      return "bg-slate-800 dark:bg-slate-700";
  }
}

function getCellTitle(dateStr: string, status: string | undefined): string {
  switch (status) {
    case "full":
      return `${dateStr}: Full ingest`;
    case "mesh":
      return `${dateStr}: MeSH filtered`;
    case "error":
      return `${dateStr}: Ingest error`;
    default:
      return `${dateStr}: No data`;
  }
}

/** Build the weeks grid for the last N weeks. */
function buildGrid(weeks: number) {
  const today = new Date();
  // Find the most recent Saturday (end of week in GitHub style, Sun=0)
  const endDay = new Date(today);
  endDay.setDate(endDay.getDate() + (6 - endDay.getDay()));

  const startDay = new Date(endDay);
  startDay.setDate(startDay.getDate() - (weeks * 7 - 1));
  // Align to Sunday
  startDay.setDate(startDay.getDate() - startDay.getDay());

  const grid: string[][] = []; // grid[week][dayOfWeek] = "YYYY-MM-DD"
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
  if (currentWeek.length > 0) {
    grid.push(currentWeek);
  }

  return grid;
}

/** Find month label positions from the grid. */
function monthLabels(grid: string[][]) {
  const labels: { label: string; col: number }[] = [];
  let lastMonth = -1;
  for (let w = 0; w < grid.length; w++) {
    const firstDate = grid[w][0];
    const month = new Date(firstDate).getMonth();
    if (month !== lastMonth) {
      labels.push({ label: MONTH_LABELS[month], col: w });
      lastMonth = month;
    }
  }
  return labels;
}

export function CoverageHeatmap() {
  const [coverage, setCoverage] = useState<Coverage>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("/api/pipeline/coverage")
      .then((r) => r.json())
      .then((data) => {
        setCoverage(data);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const WEEKS = 26; // ~6 months
  const grid = buildGrid(WEEKS);
  const months = monthLabels(grid);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-2">
      {/* Month labels */}
      <div className="flex" style={{ paddingLeft: 28 }}>
        {months.map(({ label, col }, i) => {
          const nextCol = i < months.length - 1 ? months[i + 1].col : grid.length;
          const span = nextCol - col;
          return (
            <span
              key={`${label}-${col}`}
              className="text-[10px] text-slate-500 dark:text-slate-400"
              style={{ width: span * 13 }}
            >
              {label}
            </span>
          );
        })}
      </div>

      <div className="flex gap-[2px]">
        {/* Day of week labels */}
        <div className="flex flex-col gap-[2px] pr-1">
          {DAY_LABELS.map((label, i) => (
            <div key={i} className="flex h-[11px] w-5 items-center justify-end">
              <span className="text-[9px] leading-none text-slate-500 dark:text-slate-400">
                {label}
              </span>
            </div>
          ))}
        </div>

        {/* Grid */}
        {grid.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[2px]">
            {week.map((dateStr, di) => {
              const isFuture = dateStr > today;
              const status = coverage[dateStr];
              return (
                <div
                  key={dateStr}
                  className={cn(
                    "h-[11px] w-[11px] rounded-[2px]",
                    isFuture
                      ? "bg-transparent"
                      : loaded
                        ? getCellColor(status)
                        : "bg-slate-800/50 dark:bg-slate-700/50",
                  )}
                  title={isFuture ? "" : getCellTitle(dateStr, status)}
                  // only fill slots up to row length of 7
                  style={di >= 7 ? { display: "none" } : undefined}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 pt-1">
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-slate-800 dark:bg-slate-700" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">No data</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-amber-500" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">MeSH</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-green-500" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">Full</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-red-500" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">Error</span>
        </div>
      </div>
    </div>
  );
}
