"use client";

import { useState, useTransition } from "react";
import type { PipelineRun } from "@prisma/client";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ClientTimestamp } from "@/components/client-timestamp";
import { formatDuration, formatCost } from "@/lib/utils";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";

type Props = {
  runs: PipelineRun[];
  clearAction: () => Promise<{ ok: true; message: string } | { ok: false; error: string }>;
};

function formatDateRange(from: Date | string | null, to: Date | string | null): string {
  if (!from && !to) return "-";
  const fmt = (d: Date | string) => new Date(d).toISOString().slice(0, 10);
  if (from && to) return `${fmt(from)} → ${fmt(to)}`;
  if (from) return `${fmt(from)} →`;
  return `→ ${fmt(to!)}`;
}

export function RunHistoryTable({ runs, clearAction }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [clearMsg, setClearMsg] = useState<string | null>(null);

  if (runs.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-slate-500">No pipeline runs recorded.</p>
        {clearMsg && <p className="text-xs text-slate-500">{clearMsg}</p>}
      </div>
    );
  }

  function toggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  // Flatten rows so every element in the array is a <TableRow> with a key
  const rows: React.ReactNode[] = [];
  for (const run of runs) {
    const errors = Array.isArray(run.errors) ? run.errors : [];
    const isExpanded = expandedId === run.id;

    rows.push(
      <TableRow
        key={run.id}
        className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"
        onClick={() => toggle(run.id)}
      >
        <TableCell className="w-6 px-2">
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
          )}
        </TableCell>
        <TableCell className="text-xs">
          <ClientTimestamp date={run.startedAt} />
        </TableCell>
        <TableCell className="text-xs whitespace-nowrap">
          {formatDateRange(run.fromDate, run.toDate)}
        </TableCell>
        <TableCell className="text-xs">
          {formatDuration(run.startedAt, run.finishedAt)}
        </TableCell>
        <TableCell className="text-xs">{run.papersIngested}</TableCell>
        <TableCell className="text-xs">
          {errors.length > 0 ? (
            <Badge variant="destructive" className="text-[10px]">
              {errors.length}
            </Badge>
          ) : (
            <span className="text-green-600 dark:text-green-400">0</span>
          )}
        </TableCell>
      </TableRow>,
    );

    if (isExpanded) {
      rows.push(
        <TableRow key={`${run.id}-detail`}>
          <TableCell colSpan={7} className="bg-slate-50 px-6 py-3 dark:bg-slate-800/50">
            <RunDetail run={run} errors={errors} />
          </TableCell>
        </TableRow>,
      );
    }
  }

  function handleClear() {
    if (!confirm("Clear all pipeline run history? This cannot be undone.")) return;
    startTransition(async () => {
      const res = await clearAction();
      if (res.ok) {
        setClearMsg(res.message);
        window.location.href = "/pipeline";
      } else {
        setClearMsg(res.error);
      }
    });
  }

  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-6" />
            <TableHead>Started</TableHead>
            <TableHead>Date Range</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Ingested</TableHead>
            <TableHead>Errors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>{rows}</TableBody>
      </Table>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="text-xs text-red-600 hover:text-red-700 dark:text-red-400"
          onClick={handleClear}
          disabled={isPending}
        >
          <Trash2 className="mr-1.5 h-3 w-3" />
          {isPending ? "Clearing…" : "Clear History"}
        </Button>
        {clearMsg && (
          <span className="text-xs text-slate-500">{clearMsg}</span>
        )}
      </div>
    </div>
  );
}

function fmtBacklog(value: number, backlogKey: string, backlog: Record<string, number> | null): string {
  const bl = backlog?.[backlogKey] ?? 0;
  if (bl === 0) return String(value);
  const fresh = value - bl;
  return `${value} (${fresh} in range + ${bl} prior)`;
}

function RunDetail({ run, errors }: { run: PipelineRun; errors: unknown[] }) {
  const backlog = (run.backlogStats as Record<string, number> | null) ?? null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-x-6 gap-y-2 text-xs">
        <Stat label="Papers ingested" value={run.papersIngested} />
        <Stat label="After dedup" value={run.papersAfterDedup} />
        <Stat label="Coarse filter passed" value={fmtBacklog(run.papersCoarsePassed, "coarse_filter", backlog)} />
        <Stat label="Full text retrieved" value={fmtBacklog(run.papersFulltextRetrieved, "fulltext", backlog)} />
        <Stat label="Methods analysed" value={fmtBacklog(run.papersMethodsAnalysed, "methods_analysis", backlog)} />
        <Stat label="Enriched" value={fmtBacklog(run.papersEnriched, "enrichment", backlog)} />
        <Stat label="Adjudicated" value={fmtBacklog(run.papersAdjudicated, "adjudication", backlog)} />
        <Stat label="Total cost" value={formatCost(run.totalCostUsd)} />
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs">
        {run.currentStage && (
          <span className="text-slate-500 dark:text-slate-400">
            Final stage: <span className="font-medium text-slate-700 dark:text-slate-200">{run.currentStage}</span>
          </span>
        )}
        {run.pubmedQueryMode && (
          <span className="text-slate-500 dark:text-slate-400">
            PubMed:{" "}
            <Badge
              variant={run.pubmedQueryMode === "all" ? "default" : "outline"}
              className="text-[10px]"
            >
              {run.pubmedQueryMode === "all" ? "Full" : "MeSH"}
            </Badge>
          </span>
        )}
        <span className="text-slate-500 dark:text-slate-400">
          Trigger: <Badge variant="outline" className="text-[10px]">{run.trigger}</Badge>
        </span>
      </div>

      {errors.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs font-medium text-red-600 dark:text-red-400">
            {errors.length} error{errors.length > 1 ? "s" : ""}
          </p>
          {errors.map((e, i) => (
            <p
              key={`error-${i}-${String(e).slice(0, 20)}`}
              className="rounded bg-red-50 px-3 py-1.5 font-mono text-[11px] text-red-700 dark:bg-red-900/30 dark:text-red-400"
            >
              {String(e)}
            </p>
          ))}
        </div>
      ) : (
        <p className="text-xs text-green-600 dark:text-green-400">
          No errors
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span className="text-slate-500 dark:text-slate-400">{label}: </span>
      <span className="font-medium text-slate-700 dark:text-slate-200">{value}</span>
    </div>
  );
}
