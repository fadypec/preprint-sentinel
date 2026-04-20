"use client";

import { useState } from "react";
import type { Paper } from "@prisma/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn, parseDimensions, computeAggregateScore, languageName } from "@/lib/utils";
import { riskStyle } from "@/lib/risk-colors";
import { formatDate, sourceServerLabel } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import { DimensionBar } from "@/components/dimension-bar";

const DIMENSION_LABELS: Record<string, string> = {
  pathogen_enhancement: "Pathogen Enhancement",
  synthesis_barrier_lowering: "Synthesis Barrier Lowering",
  select_agent_relevance: "Select Agent Relevance",
  novel_technique: "Novel Technique",
  information_hazard: "Information Hazard",
  defensive_framing: "Defensive Framing",
};

type PaperCardProps = {
  paper: Paper;
};

export function PaperCard({ paper }: PaperCardProps) {
  const style = riskStyle(paper.riskTier);
  const isTranslated = paper.language != null && paper.language !== "eng" && paper.originalTitle != null;
  const stage2 = paper.stage2Result as {
    summary?: string;
    dimensions?: unknown;
    aggregate_score?: number;
    _error?: string;
  } | null;
  const stage3 = paper.stage3Result as { summary?: string; _error?: string } | null;
  const summary = stage3?.summary ?? stage2?.summary ?? null;

  // Detect processing errors
  const hasError = !!(stage2?._error || stage3?._error || paper.needsManualReview);

  // Parse dimensions (may be a JSON string or object)
  const dimensions = parseDimensions(stage2?.dimensions);
  const topDimensions = Object.entries(dimensions)
    .filter(([, d]) => d.score >= 1)
    .sort(([, a], [, b]) => b.score - a.score)
    .slice(0, 3);

  // Fall back to stage2 aggregate_score, then compute from dimensions
  const score =
    paper.aggregateScore ||
    stage2?.aggregate_score ||
    computeAggregateScore(dimensions) ||
    null;

  // Format author list
  type AuthorEntry = { name?: string };
  const authorList = Array.isArray(paper.authors)
    ? (paper.authors as unknown as AuthorEntry[])
    : null;
  const authors = authorList
    ? authorList
        .slice(0, 3)
        .map((a) => a.name ?? "Unknown")
        .join(", ") + (authorList.length > 3 ? " et al." : "")
    : paper.correspondingAuthor ?? "Unknown authors";

  const [expanded, setExpanded] = useState(false);
  const allDimensions = Object.entries(dimensions);

  return (
    <Card
      className={cn(
        "border-l-4 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800",
        style.border
      )}
      role="article"
      aria-label={`${paper.title}. Risk tier: ${style.label}, score ${paper.aggregateScore ?? 0} out of 18`}
    >
      <a href={`/paper/${paper.id}`} className="block no-underline">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {paper.title}
              {isTranslated && (
                <span className="ml-2 inline-flex rounded bg-blue-100 px-1.5 py-0.5 align-middle text-[10px] font-normal text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                  AI translated from {languageName(paper.language!)}
                </span>
              )}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {authors} &middot; {paper.correspondingInstitution ?? ""} &middot;{" "}
              {sourceServerLabel(paper.sourceServer)} &middot; {formatDate(paper.postedDate)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {hasError && (
              <span
                className="text-amber-500 dark:text-amber-400"
                aria-label="Processing errors — assessment may be incomplete"
              >
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              </span>
            )}
            <Badge className={cn(style.badge)} aria-label={`Risk tier: ${style.label}`}>
              {style.label}
            </Badge>
          </div>
        </div>

        {summary && (
          <p className="mt-2 line-clamp-2 text-xs text-slate-600 dark:text-slate-300">
            {summary}
          </p>
        )}

        {(topDimensions.length > 0 || score != null || paper.riskTier === "refused") && (
          <div className="mt-2 flex flex-wrap gap-1">
            {topDimensions.map(([name, dim]) => (
              <span
                key={name}
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px]",
                  dim.score >= 3
                    ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                    : dim.score >= 2
                      ? "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400"
                      : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
                )}
              >
                {name.replace(/_/g, " ")}: {dim.score}
              </span>
            ))}
            {score != null ? (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                Score: {score}/18
              </span>
            ) : paper.riskTier === "refused" ? (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium italic text-slate-500 dark:bg-slate-700 dark:text-slate-400">
                Score: Undefined
              </span>
            ) : null}
          </div>
        )}
      </a>

      {allDimensions.length > 0 && (
        <div className="mt-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            aria-expanded={expanded}
            aria-controls={`dimensions-${paper.id}`}
            className="text-[11px] font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
          >
            {expanded ? "Hide dimensions" : "Show dimensions"}
          </button>
          {expanded && (
            <div id={`dimensions-${paper.id}`} className="mt-2 rounded-lg border border-slate-200 bg-slate-50/50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
              {allDimensions.map(([name, dim]) => (
                <DimensionBar
                  key={name}
                  label={DIMENSION_LABELS[name] ?? name.replace(/_/g, " ")}
                  score={dim.score}
                  justification={dim.justification}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
