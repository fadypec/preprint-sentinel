"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Play, Pause, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

type PipelineStatus = {
  running: boolean;
  paused: boolean;
  next_run_time: string | null;
};

type Props = {
  initialStatus: PipelineStatus | null;
};

export function PipelineControls({ initialStatus }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [isPending, startTransition] = useTransition();
  const [hour, setHour] = useState(6);
  const [minute, setMinute] = useState(0);

  function runNow() {
    startTransition(async () => {
      await fetch("/api/pipeline", { method: "POST" });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  function togglePause() {
    startTransition(async () => {
      const endpoint = status?.paused
        ? "/api/pipeline/resume"
        : "/api/pipeline/pause";
      await fetch(endpoint, { method: "POST" });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  function updateSchedule() {
    startTransition(async () => {
      await fetch("/api/pipeline/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hour, minute }),
      });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  const statusDot = status
    ? status.paused
      ? "bg-yellow-500"
      : status.running
        ? "bg-green-500"
        : "bg-slate-400"
    : "bg-slate-400";
  const statusLabel = status
    ? status.paused
      ? "Paused"
      : status.running
        ? "Running"
        : "Idle"
    : "Unreachable";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className={cn("h-3 w-3 rounded-full", statusDot)} />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {statusLabel}
        </span>
      </div>

      {status?.next_run_time && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Next scheduled: {new Date(status.next_run_time).toLocaleString()}
        </p>
      )}

      <div className="flex gap-2">
        <Button size="sm" onClick={runNow} disabled={isPending}>
          <Play className="mr-1 h-3 w-3" />
          Run Now
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={togglePause}
          disabled={isPending}
        >
          {status?.paused ? (
            <>
              <RefreshCw className="mr-1 h-3 w-3" /> Resume
            </>
          ) : (
            <>
              <Pause className="mr-1 h-3 w-3" /> Pause
            </>
          )}
        </Button>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          Daily Run Time (UTC)
        </p>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={0}
            max={23}
            value={hour}
            onChange={(e) => setHour(parseInt(e.target.value, 10))}
            className="w-16"
            aria-label="Hour"
          />
          <span className="text-slate-500">:</span>
          <Input
            type="number"
            min={0}
            max={59}
            value={minute}
            onChange={(e) => setMinute(parseInt(e.target.value, 10))}
            className="w-16"
            aria-label="Minute"
          />
          <Button
            size="sm"
            variant="outline"
            onClick={updateSchedule}
            disabled={isPending}
          >
            Update
          </Button>
        </div>
      </div>
    </div>
  );
}
