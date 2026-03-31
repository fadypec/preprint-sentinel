import { PaperCard } from "@/components/paper-card";
import { PaperFilters } from "@/components/paper-filters";
import { buttonVariants } from "@/components/ui/button";
import { queryPapers } from "@/lib/queries/papers";
import { cn } from "@/lib/utils";
import Link from "next/link";

type Props = {
  searchParams: Promise<{
    page?: string;
    tier?: string;
    source?: string;
    status?: string;
    q?: string;
  }>;
};

function buildPaginationHref(
  targetPage: number,
  filters: { tier?: string; source?: string; status?: string; q?: string },
): string {
  const p = new URLSearchParams();
  p.set("page", String(targetPage));
  if (filters.tier && filters.tier !== "all") p.set("tier", filters.tier);
  if (filters.source && filters.source !== "all") p.set("source", filters.source);
  if (filters.status && filters.status !== "all") p.set("status", filters.status);
  if (filters.q) p.set("q", filters.q);
  return `/?${p.toString()}`;
}

export default async function DailyFeedPage({ searchParams }: Props) {
  const params = await searchParams;
  const page = parseInt(params.page ?? "1", 10) || 1;
  const tier = params.tier;
  const source = params.source;
  const status = params.status;
  const search = params.q?.trim();

  const { papers, total, totalPages } = await queryPapers({
    page,
    tier,
    source,
    status,
    search,
  });

  const filterState = { tier, source, status, q: search };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Daily Feed
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {total} papers flagged &middot;{" "}
            {new Date().toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        </div>
      </div>

      <div className="mb-4">
        <PaperFilters />
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
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              Previous
            </Link>
          ) : (
            <span
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "pointer-events-none opacity-50",
              )}
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
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              Next
            </Link>
          ) : (
            <span
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "pointer-events-none opacity-50",
              )}
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
