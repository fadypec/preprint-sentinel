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

type Props = {
  runs: PipelineRun[];
};

export function RunHistoryTable({ runs }: Props) {
  if (runs.length === 0) {
    return <p className="text-sm text-slate-500">No pipeline runs recorded.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
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
      <TableBody>
        {runs.map((run) => {
          const errors = Array.isArray(run.errors) ? run.errors : [];
          return (
            <TableRow key={run.id}>
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
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
