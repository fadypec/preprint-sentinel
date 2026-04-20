import { prisma } from "@/lib/prisma";
import { Badge } from "@/components/ui/badge";
import { riskStyle } from "@/lib/risk-colors";
import { cn, formatDate } from "@/lib/utils";

type Props = {
  paperId: string;
  institution: string | null;
  firstAuthorSurname: string | null;
};

type AuthorEntry = { name?: string };

function extractSurname(authors: unknown): string | null {
  if (!Array.isArray(authors) || authors.length === 0) return null;
  const name = (authors[0] as AuthorEntry).name ?? "";
  const parts = name.split(",");
  return parts[0]?.trim() || null;
}

/**
 * Server component — queries the database for papers that share the same
 * institution or first author surname. No client JS needed.
 */
export async function RelatedPapers({
  paperId,
  institution,
  firstAuthorSurname,
}: Props) {
  if (!institution && !firstAuthorSurname) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No author or institution data to find related papers.
      </p>
    );
  }

  // Build OR conditions for related paper search
  const orConditions: Record<string, unknown>[] = [];
  if (institution) {
    orConditions.push({ correspondingInstitution: institution });
  }
  if (firstAuthorSurname) {
    // Search authors JSONB for matching surname using string_contains on serialized JSON
    // This is a rough match — good enough for "related papers" suggestions
    orConditions.push({
      authors: { string_contains: firstAuthorSurname },
    });
  }

  const related = await prisma.paper.findMany({
    where: {
      id: { not: paperId },
      isDuplicateOf: null,
      coarseFilterPassed: true,
      OR: orConditions,
    },
    orderBy: { postedDate: "desc" },
    take: 5,
    select: {
      id: true,
      title: true,
      correspondingInstitution: true,
      authors: true,
      riskTier: true,
      postedDate: true,
      sourceServer: true,
    },
  });

  if (related.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No related papers found.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {related.map((p) => {
        const style = riskStyle(p.riskTier);
        const surname = extractSurname(p.authors);
        const matchType =
          institution && p.correspondingInstitution === institution
            ? "institution"
            : "author";

        return (
          <a
            key={p.id}
            href={`/paper/${p.id}`}
            aria-label={`View related paper: ${p.title}`}
            className="block rounded-md border border-slate-200 p-3 text-sm no-underline transition-colors hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium text-slate-800 dark:text-slate-200 line-clamp-2">
                {p.title}
              </span>
              {p.riskTier && (
                <Badge className={cn("shrink-0 text-[10px]", style.badge)}>
                  {style.label}
                </Badge>
              )}
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span>{formatDate(p.postedDate)}</span>
              <span>&middot;</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-700">
                {matchType === "institution" ? "same institution" : `author: ${surname}`}
              </span>
            </div>
          </a>
        );
      })}
    </div>
  );
}
