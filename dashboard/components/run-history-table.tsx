"use client";

import { useState } from "react";
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
import { ClientTimestamp } from "@/components/client-timestamp";
import { formatDuration, formatCost } from "@/lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";

type Props = {
  runs: PipelineRun[];
};

export function RunHistoryTable({ runs }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (runs.length === 0) {
    return <p className="text-sm text-slate-500">No pipeline runs recorded.</p>;
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
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
          )}
        </TableCell>
        <TableCell className="text-xs">
          <ClientTimestamp date={run.startedAt} />
        </TableCell>
        <TableCell className="text-xs">
          {formatDuration(run.startedAt, run.finishedAt)}
        </TableCell>
        <TableCell className="text-xs">{run.papersIngested}</TableCell>
        <TableCell className="text-xs">
          {run.papersCoarsePassed}
        </TableCell>
        <TableCell className="text-xs">
          {run.papersAdjudicated}
        </TableCell>
        <TableCell className="text-xs">
          {errors.length > 0 ? (
            <Badge variant="destructive" className="text-[10px]">
              {errors.length}
            </Badge>
          ) : (
            <span className="text-green-600 dark:text-green-400">0</span>
          )}
        </TableCell>
        <TableCell className="text-xs">
          {formatCost(run.totalCostUsd)}
        </TableCell>
        <TableCell className="text-xs">
          {run.pubmedQueryMode ? (
            <Badge
              variant={run.pubmedQueryMode === "all" ? "default" : "outline"}
              className="text-[10px]"
            >
              {run.pubmedQueryMode === "all" ? "Full" : "MeSH"}
            </Badge>
          ) : (
            <span className="text-slate-400">-</span>
          )}
        </TableCell>
        <TableCell className="text-xs">
          <Badge variant="outline" className="text-[10px]">
            {run.trigger}
          </Badge>
        </TableCell>
      </TableRow>,
    );

    if (isExpanded) {
      rows.push(
        <TableRow key={`${run.id}-detail`}>
          <TableCell colSpan={10} className="bg-slate-50 px-6 py-3 dark:bg-slate-800/50">
            <RunDetail run={run} errors={errors} />
          </TableCell>
        </TableRow>,
      );
    }
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-6" />
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Ingested</TableHead>
          <TableHead>Passed</TableHead>
          <TableHead>Adjudicated</TableHead>
          <TableHead>Errors</TableHead>
          <TableHead>Cost</TableHead>
          <TableHead>PubMed</TableHead>
          <TableHead>Trigger</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>{rows}</TableBody>
    </Table>
  );
}

function RunDetail({ run, errors }: { run: PipelineRun; errors: unknown[] }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-x-6 gap-y-2 text-xs">
        <Stat label="Papers ingested" value={run.papersIngested} />
        <Stat label="After dedup" value={run.papersAfterDedup} />
        <Stat label="Coarse filter passed" value={run.papersCoarsePassed} />
        <Stat label="Full text retrieved" value={run.papersFulltextRetrieved} />
        <Stat label="Methods analysed" value={run.papersMethodsAnalysed} />
        <Stat label="Enriched" value={run.papersEnriched} />
        <Stat label="Adjudicated" value={run.papersAdjudicated} />
        <Stat label="Total cost" value={formatCost(run.totalCostUsd)} />
      </div>

      {run.currentStage && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Final stage: <span className="font-medium">{run.currentStage}</span>
        </p>
      )}

      {errors.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs font-medium text-red-600 dark:text-red-400">
            {errors.length} error{errors.length > 1 ? "s" : ""}
          </p>
          {errors.map((e, i) => (
            <p
              key={i}
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
