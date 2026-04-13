"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Play, Square, Loader2, Calendar, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { PipelineProgress } from "@/components/pipeline-progress";

type PipelineStatus = {
  running: boolean;
  paused: boolean;
};

type ActionResult =
  | { ok: true; message: string }
  | { ok: false; error: string };

type Props = {
  initialStatus: PipelineStatus | null;
  triggerAction: (from: string, to: string, includeBacklog: boolean) => Promise<ActionResult>;
  cancelAction: () => Promise<ActionResult>;
  reprocessAction: () => Promise<ActionResult>;
  pubmedMode: string;
  togglePubmedMode: () => Promise<string>;
};

/** Format a Date to YYYY-MM-DD for input[type=date]. */
function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function PipelineControls({
  initialStatus,
  triggerAction,
  cancelAction,
  reprocessAction,
  pubmedMode: initialPubmedMode,
  togglePubmedMode,
}: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [pending, setPending] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [currentPubmedMode, setCurrentPubmedMode] = useState(initialPubmedMode);
  const [toggling, setToggling] = useState(false);
  const [includeBacklog, setIncludeBacklog] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);

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
      const result = await triggerAction(fromDate, toDate, includeBacklog);
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

  async function stopPipeline() {
    setCancelling(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await cancelAction();
      if (result.ok) {
        setSuccess(result.message);
        setStatus({ running: false, paused: false });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel");
    } finally {
      setCancelling(false);
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

      {/* PubMed mode */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          PubMed:
        </span>
        <button
          type="button"
          onClick={async () => {
            setToggling(true);
            try {
              const newMode = await togglePubmedMode();
              setCurrentPubmedMode(newMode);
            } finally {
              setToggling(false);
            }
          }}
          disabled={toggling || pending || isRunning}
          className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Badge variant={currentPubmedMode === "all" ? "default" : "outline"}>
            {currentPubmedMode === "all" ? "Full" : "MeSH Filtered"}
          </Badge>
        </button>
        <span className="text-[10px] text-slate-400">
          {currentPubmedMode === "all"
            ? "~30K papers/day"
            : "~800 papers/day"}
        </span>
      </div>

      {/* Include backlog */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Backlog:
        </span>
        <button
          type="button"
          onClick={() => setIncludeBacklog((v) => !v)}
          disabled={pending || isRunning}
          className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Badge variant={includeBacklog ? "default" : "outline"}>
            {includeBacklog ? "Include" : "Skip"}
          </Badge>
        </button>
        <span className="text-[10px] text-slate-400">
          {includeBacklog
            ? "Process all pending papers"
            : "Only papers in date range"}
        </span>
      </div>

      {/* Run / Stop / Reprocess buttons */}
      <div className="flex gap-2">
        {isRunning ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={stopPipeline}
            disabled={cancelling}
          >
            {cancelling ? (
              <>
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                Stopping...
              </>
            ) : (
              <>
                <Square className="mr-1 h-3 w-3" />
                Stop Pipeline
              </>
            )}
          </Button>
        ) : (
          <>
            <Button
              size="sm"
              onClick={runPipeline}
              disabled={pending || reprocessing}
            >
              {pending ? (
                <>
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="mr-1 h-3 w-3" />
                  Run Pipeline
                </>
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={pending || reprocessing}
              onClick={async () => {
                setReprocessing(true);
                setError(null);
                setSuccess(null);
                try {
                  const result = await reprocessAction();
                  if (result.ok) setSuccess(result.message);
                  else setError(result.error);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed");
                } finally {
                  setReprocessing(false);
                }
              }}
            >
              {reprocessing ? (
                <>
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  Resetting...
                </>
              ) : (
                <>
                  <RefreshCw className="mr-1 h-3 w-3" />
                  Fix Errors
                </>
              )}
            </Button>
          </>
        )}
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

      {/* Progress — shown inline as soon as a run is active */}
      {isRunning && (
        <div className="border-t pt-4">
          <h3 className="mb-3 text-xs font-semibold text-slate-700 dark:text-slate-300">
            Progress
          </h3>
          <PipelineProgress initialRunning />
        </div>
      )}
    </div>
  );
}
