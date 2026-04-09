import { PaperCard } from "@/components/paper-card";
import { PaperFilters } from "@/components/paper-filters";
import { queryPapers } from "@/lib/queries/papers";
import { cn } from "@/lib/utils";
import Link from "next/link";

export const dynamic = "force-dynamic";

const paginationBase =
  "inline-flex shrink-0 items-center justify-center rounded-lg text-sm font-medium border border-border bg-background h-7 px-2.5 text-[0.8rem]";
const paginationEnabled =
  "hover:bg-muted hover:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50";
const paginationDisabled = "pointer-events-none opacity-50";

type Props = {
  searchParams: Promise<{
    page?: string;
    tier?: string;
    source?: string;
    status?: string;
    q?: string;
    needs_review?: string;
    sort?: string;
  }>;
};

function buildPaginationHref(
  targetPage: number,
  filters: { tier?: string; source?: string; status?: string; q?: string; sort?: string },
): string {
  const p = new URLSearchParams();
  p.set("page", String(targetPage));
  if (filters.tier && filters.tier !== "all") p.set("tier", filters.tier);
  if (filters.source && filters.source !== "all") p.set("source", filters.source);
  if (filters.status && filters.status !== "all") p.set("status", filters.status);
  if (filters.q) p.set("q", filters.q);
  if (filters.sort && filters.sort !== "date_desc") p.set("sort", filters.sort);
  return `/?${p.toString()}`;
}

export default async function DailyFeedPage({ searchParams }: Props) {
  const params = await searchParams;
  const page = parseInt(params.page ?? "1", 10) || 1;
  const tier = params.tier;
  const source = params.source;
  const status = params.status;
  const search = params.q?.trim();
  const needsReview = params.needs_review;
  const sort = params.sort;

  const { papers, total, totalIngested, totalPages } = await queryPapers({
    page,
    tier,
    source,
    status,
    search,
    needsReview,
    sort,
  });

  const filterState = { tier, source, status, q: search, needsReview, sort };
  const flaggedPct = totalIngested > 0 ? ((total / totalIngested) * 100).toFixed(1) : "0";

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Daily Feed
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {total} flagged of {totalIngested.toLocaleString()} ingested ({flaggedPct}%) &middot;{" "}
            {new Date().toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        </div>
      </div>

      <div className="mb-4">
        <PaperFilters
          tier={tier ?? "all"}
          source={source ?? "all"}
          status={status ?? "all"}
          q={search ?? ""}
          needsReview={needsReview ?? ""}
          sort={sort ?? "date_desc"}
        />
      </div>

      <div className="flex flex-col gap-3" role="feed" aria-label="Flagged papers">
        {papers.map((paper) => (
          <PaperCard key={paper.id} paper={paper} />
        ))}
        {papers.length === 0 && (
          <p className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">
            No papers match your filters.
          </p>
        )}
      </div>

      {totalPages > 1 && (
        <nav className="mt-6 flex items-center justify-center gap-2" aria-label="Pagination">
          {page > 1 ? (
            <Link
              href={buildPaginationHref(page - 1, filterState)}
              className={cn(paginationBase, paginationEnabled)}
            >
              Previous
            </Link>
          ) : (
            <span
              className={cn(paginationBase, paginationDisabled)}
              aria-disabled="true"
            >
              Previous
            </span>
          )}
          <span className="text-sm text-slate-500 dark:text-slate-400">
            Page {page} of {totalPages}
          </span>
          {page < totalPages ? (
            <Link
              href={buildPaginationHref(page + 1, filterState)}
              className={cn(paginationBase, paginationEnabled)}
            >
              Next
            </Link>
          ) : (
            <span
              className={cn(paginationBase, paginationDisabled)}
              aria-disabled="true"
            >
              Next
            </span>
          )}
        </nav>
      )}
    </div>
  );
}
