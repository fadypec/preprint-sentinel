import { DimensionBar } from "@/components/dimension-bar";
import { ReviewStatusSelect } from "@/components/review-status-select";
import { Badge } from "@/components/ui/badge";
import { riskStyle } from "@/lib/risk-colors";
import { cn, parseDimensions, computeAggregateScore } from "@/lib/utils";
import { ExternalLink } from "lucide-react";
import type { Paper } from "@prisma/client";

const dimensionLabels: Record<string, string> = {
  pathogen_enhancement: "Pathogen Enhancement",
  synthesis_barrier_lowering: "Synthesis Barrier",
  select_agent_relevance: "Select Agent",
  novel_technique: "Novel Technique",
  information_hazard: "Info Hazard",
  defensive_framing: "Defensive Framing",
};

type RiskPanelProps = {
  paper: Paper;
};

export function RiskPanel({ paper }: RiskPanelProps) {
  const style = riskStyle(paper.riskTier);
  const stage2 = paper.stage2Result as {
    dimensions?: unknown;
    aggregate_score?: number;
  } | null;
  const dimensions = parseDimensions(stage2?.dimensions);

  // Fall back to stage2 aggregate_score, then compute from dimensions
  const score =
    paper.aggregateScore ||
    stage2?.aggregate_score ||
    computeAggregateScore(dimensions) ||
    0;

  const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;

  return (
    <div className="sticky top-6 space-y-4">
      {/* Aggregate badge */}
      <div className="text-center">
        <Badge className={cn("text-lg px-3 py-1", style.badge)}>
          {style.label} &middot; {score}/18
        </Badge>
      </div>

      {/* Risk dimensions */}
      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Risk Dimensions
        </h3>
        {Object.entries(dimensionLabels).map(([key, label]) => {
          const dim = dimensions[key];
          return (
            <DimensionBar
              key={key}
              label={label}
              score={dim?.score ?? 0}
              justification={dim?.justification}
            />
          );
        })}
      </div>

      {/* Review status */}
      <div className="border-t border-slate-200 pt-4 dark:border-slate-700">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Review Status
        </h3>
        <ReviewStatusSelect paperId={paper.id} currentStatus={paper.reviewStatus} />
      </div>

      {/* Actions */}
      <div className="space-y-2">
        {doiUrl && (
          <a
            href={doiUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-7 w-full items-center justify-center gap-1 rounded-lg border border-border bg-background px-2.5 text-[0.8rem] font-medium transition-colors hover:bg-muted hover:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50"
          >
            <ExternalLink className="h-3 w-3" />
            Open Original
          </a>
        )}
      </div>
    </div>
  );
}
