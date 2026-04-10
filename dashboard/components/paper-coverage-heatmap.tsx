"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type DayData = { count: number; hasPubmed: boolean };
type Coverage = Record<string, DayData>;

const DAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Convert JS getDay() (Sun=0) to Monday-first index (Mon=0). */
function mondayIndex(jsDay: number): number {
  return (jsDay + 6) % 7;
}

/**
 * Color intensity based on paper count. Zero = gap (grey).
 * Low counts get lighter green, high counts get darker green.
 * No PubMed = amber tint (preprints only).
 */
function getCellColor(data: DayData | undefined): string {
  if (!data || data.count === 0) return "bg-slate-800 dark:bg-slate-700";
  if (!data.hasPubmed) {
    // Preprints only — amber scale
    if (data.count < 50) return "bg-amber-300 dark:bg-amber-800";
    if (data.count < 200) return "bg-amber-400 dark:bg-amber-700";
    return "bg-amber-500 dark:bg-amber-600";
  }
  // Full coverage — green scale
  if (data.count < 50) return "bg-green-300 dark:bg-green-800";
  if (data.count < 200) return "bg-green-400 dark:bg-green-700";
  if (data.count < 500) return "bg-green-500 dark:bg-green-600";
  return "bg-green-600 dark:bg-green-500";
}

function getCellTitle(dateStr: string, data: DayData | undefined): string {
  if (!data || data.count === 0) return `${dateStr}: No papers ingested (gap)`;
  const source = data.hasPubmed ? "preprints + PubMed" : "preprints only";
  return `${dateStr}: ${data.count} papers (${source})`;
}

/** Build the weeks grid starting on Monday. */
function buildGrid(weeks: number) {
  const today = new Date();
  const endDay = new Date(today);
  const daysUntilSunday = (7 - mondayIndex(endDay.getDay()) - 1 + 7) % 7;
  endDay.setDate(endDay.getDate() + daysUntilSunday);

  const startDay = new Date(endDay);
  startDay.setDate(startDay.getDate() - (weeks * 7 - 1));
  const startOffset = mondayIndex(startDay.getDay());
  startDay.setDate(startDay.getDate() - startOffset);

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

  const WEEKS = 26;
  const grid = buildGrid(WEEKS);
  const months = monthLabels(grid);
  const today = new Date().toISOString().slice(0, 10);

  // Count gaps (past weekdays with zero papers)
  let gaps = 0;
  for (const week of grid) {
    for (let di = 0; di < week.length && di < 5; di++) {
      // Mon-Fri only (weekdays)
      const dateStr = week[di];
      if (dateStr <= today && !coverage[dateStr]) gaps++;
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Intelligence Coverage
        </h3>
        {loaded && gaps > 0 && (
          <span className="text-xs text-red-500 dark:text-red-400">
            {gaps} weekday{gaps !== 1 ? "s" : ""} with no data
          </span>
        )}
      </div>

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
        {/* Day labels (Mon-first) */}
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
              const data = coverage[dateStr];
              return (
                <div
                  key={dateStr}
                  className={cn(
                    "h-[11px] w-[11px] rounded-[2px]",
                    isFuture
                      ? "bg-transparent"
                      : loaded
                        ? getCellColor(data)
                        : "bg-slate-800/50 dark:bg-slate-700/50",
                  )}
                  title={isFuture ? "" : getCellTitle(dateStr, data)}
                  style={di >= 7 ? { display: "none" } : undefined}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-slate-800 dark:bg-slate-700" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">No data (gap)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-amber-400 dark:bg-amber-700" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">Preprints only</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-green-400 dark:bg-green-700" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">Full coverage</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-[11px] w-[11px] rounded-[2px] bg-green-600 dark:bg-green-500" />
          <span className="text-[10px] text-slate-500 dark:text-slate-400">500+ papers</span>
        </div>
      </div>
    </div>
  );
}
