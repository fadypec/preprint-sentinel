import Link from "next/link";
import type { Paper } from "@prisma/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn, parseDimensions, languageName } from "@/lib/utils";
import { riskStyle } from "@/lib/risk-colors";
import { formatDate, sourceServerLabel } from "@/lib/utils";

type PaperCardProps = {
  paper: Paper;
};

export function PaperCard({ paper }: PaperCardProps) {
  const style = riskStyle(paper.riskTier);
  const isTranslated = paper.language != null && paper.language !== "eng" && paper.originalTitle != null;
  const stage2 = paper.stage2Result as { summary?: string; dimensions?: unknown } | null;
  const stage3 = paper.stage3Result as { summary?: string } | null;
  const summary = stage3?.summary ?? stage2?.summary ?? null;

  // Parse dimensions (may be a JSON string or object)
  const dimensions = parseDimensions(stage2?.dimensions);
  const topDimensions = Object.entries(dimensions)
    .filter(([, d]) => d.score >= 1)
    .sort(([, a], [, b]) => b.score - a.score)
    .slice(0, 3);

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

  return (
    <Link href={`/paper/${paper.id}`} className="block">
      <Card
        className={cn(
          "border-l-4 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800",
          style.border
        )}
        role="article"
        aria-label={`${paper.title}. Risk tier: ${style.label}, score ${paper.aggregateScore ?? 0} out of 18`}
      >
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
          <Badge className={cn("shrink-0", style.badge)} aria-label={`Risk tier: ${style.label}`}>
            {style.label}
          </Badge>
        </div>

        {summary && (
          <p className="mt-2 line-clamp-2 text-xs text-slate-600 dark:text-slate-300">
            {summary}
          </p>
        )}

        {paper.aggregateScore != null && (
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
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              Score: {paper.aggregateScore}/18
            </span>
          </div>
        )}
      </Card>
    </Link>
  );
}
