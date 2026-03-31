"use client";

import { useState } from "react";
import type { AssessmentLog } from "@prisma/client";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatCost } from "@/lib/utils";

type Props = {
  logs: AssessmentLog[];
};

export function AuditTrail({ logs }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (logs.length === 0) {
    return <p className="text-sm text-slate-500">No assessment logs.</p>;
  }

  return (
    <div className="space-y-2">
      {logs.map((log) => {
        const isExpanded = expandedId === log.id;
        return (
          <div
            key={log.id}
            className="rounded-md border border-slate-200 dark:border-slate-700"
          >
            <button
              className="flex w-full items-center gap-2 p-3 text-left text-xs"
              onClick={() => setExpandedId(isExpanded ? null : log.id)}
              aria-expanded={isExpanded}
            >
              {isExpanded ? (
                <ChevronDown className="h-3 w-3 shrink-0" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0" />
              )}
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {log.stage}
              </span>
              <span className="text-slate-500 dark:text-slate-400">
                {log.modelUsed} &middot; {log.promptVersion} &middot;{" "}
                {log.inputTokens + log.outputTokens} tokens &middot;{" "}
                {formatCost(log.costEstimateUsd)}
              </span>
              <span className="ml-auto text-slate-400">
                {new Date(log.createdAt).toLocaleString()}
              </span>
            </button>
            {isExpanded && (
              <div className="border-t border-slate-200 p-3 dark:border-slate-700">
                <details className="mb-2">
                  <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-400">
                    Prompt
                  </summary>
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500 dark:text-slate-400">
                    {log.promptText}
                  </pre>
                </details>
                <details>
                  <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-400">
                    Response
                  </summary>
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500 dark:text-slate-400">
                    {log.rawResponse}
                  </pre>
                </details>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
