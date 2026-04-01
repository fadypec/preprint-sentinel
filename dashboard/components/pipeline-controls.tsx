"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Play, Pause, Loader2, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

type PipelineStatus = {
  running: boolean;
  paused: boolean;
};

type TriggerResult =
  | { ok: true; message: string }
  | { ok: false; error: string };

type Props = {
  initialStatus: PipelineStatus | null;
  triggerAction: (from: string, to: string) => Promise<TriggerResult>;
};

/** Format a Date to YYYY-MM-DD for input[type=date]. */
function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function PipelineControls({ initialStatus, triggerAction }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Default range: last 2 days → today
  const today = fmtDate(new Date());
  const twoDaysAgo = fmtDate(
    new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
  );
  const [fromDate, setFromDate] = useState(twoDaysAgo);
  const [toDate, setToDate] = useState(today);

  async function runPipeline() {
    setPending(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await triggerAction(fromDate, toDate);
      if (result.ok) {
        setSuccess(result.message);
        setStatus({ running: true, paused: false });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start");
    } finally {
      setPending(false);
    }
  }

  const isRunning = status?.running ?? false;

  const statusDot = isRunning ? "bg-green-500 animate-pulse" : "bg-slate-400";
  const statusLabel = isRunning ? "Running" : "Idle";

  return (
    <div className="space-y-4">
      {/* Status indicator */}
      <div className="flex items-center gap-2">
        <div className={cn("h-3 w-3 rounded-full", statusDot)} />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {statusLabel}
        </span>
        {!pending && (
          <a
            href="/pipeline"
            className="ml-auto text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          >
            Refresh
          </a>
        )}
      </div>

      {/* Date range */}
      <div>
        <p className="mb-1 flex items-center gap-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          <Calendar className="h-3 w-3" />
          Date Range
        </p>
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="h-8 w-36 text-xs"
            aria-label="From date"
            disabled={pending || isRunning}
          />
          <span className="text-xs text-slate-400">to</span>
          <Input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="h-8 w-36 text-xs"
            aria-label="To date"
            disabled={pending || isRunning}
          />
        </div>
      </div>

      {/* Run button */}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={runPipeline}
          disabled={pending || isRunning}
        >
          {pending ? (
            <>
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Starting...
            </>
          ) : isRunning ? (
            <>
              <Pause className="mr-1 h-3 w-3" />
              Running...
            </>
          ) : (
            <>
              <Play className="mr-1 h-3 w-3" />
              Run Pipeline
            </>
          )}
        </Button>
      </div>

      {/* Feedback */}
      {error && (
        <p className="rounded bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </p>
      )}
      {success && (
        <p className="rounded bg-green-50 px-3 py-2 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-400">
          {success}
        </p>
      )}
    </div>
  );
}
