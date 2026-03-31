import { prisma } from "@/lib/prisma";
import { PipelineStage, Prisma, RiskTier, SourceServer, ReviewStatus } from "@prisma/client";
import { PaperCard } from "@/components/paper-card";
import { PaperFilters } from "@/components/paper-filters";
import { buttonVariants } from "@/components/ui/button";
import { buildSearchQuery } from "@/lib/search";
import { cn } from "@/lib/utils";
import Link from "next/link";

const PAGE_SIZE = 20;

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
  const page = Math.max(1, parseInt(params.page ?? "1", 10));
  const tier = params.tier;
  const source = params.source;
  const status = params.status;
  const search = params.q?.trim();

  const where: Prisma.PaperWhereInput = {
    pipelineStage: { not: PipelineStage.ingested },
    isDuplicateOf: null,
  };

  if (tier && tier !== "all") {
    where.riskTier = tier as RiskTier;
  }
  if (source && source !== "all") {
    where.sourceServer = source as SourceServer;
  }
  if (status && status !== "all") {
    where.reviewStatus = status as ReviewStatus;
  }

  let papers;
  let total: number;

  if (search) {
    const tsquery = buildSearchQuery(search);
    if (tsquery) {
      const countResult = await prisma.$queryRaw<[{ count: bigint }]>`
        SELECT COUNT(*) as count FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
          ${tier && tier !== "all" ? Prisma.sql`AND risk_tier = ${tier}::risk_tier` : Prisma.empty}
          ${source && source !== "all" ? Prisma.sql`AND source_server = ${source}::source_server` : Prisma.empty}
          ${status && status !== "all" ? Prisma.sql`AND review_status = ${status}::review_status` : Prisma.empty}
      `;
      total = Number(countResult[0].count);
      papers = await prisma.$queryRaw`
        SELECT * FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
          ${tier && tier !== "all" ? Prisma.sql`AND risk_tier = ${tier}::risk_tier` : Prisma.empty}
          ${source && source !== "all" ? Prisma.sql`AND source_server = ${source}::source_server` : Prisma.empty}
          ${status && status !== "all" ? Prisma.sql`AND review_status = ${status}::review_status` : Prisma.empty}
        ORDER BY ts_rank(search_vector, to_tsquery('english', ${tsquery})) DESC
        LIMIT ${PAGE_SIZE} OFFSET ${(page - 1) * PAGE_SIZE}
      `;
    } else {
      papers = [];
      total = 0;
    }
  } else {
    total = await prisma.paper.count({ where });
    papers = await prisma.paper.findMany({
      where,
      orderBy: [
        { riskTier: { sort: "desc", nulls: "last" } },
        { postedDate: "desc" },
      ],
      take: PAGE_SIZE,
      skip: (page - 1) * PAGE_SIZE,
    });
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
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
        {(papers as { id: string }[]).map((paper) => (
          <PaperCard key={paper.id} paper={paper as Parameters<typeof PaperCard>[0]["paper"]} />
        ))}
        {(papers as unknown[]).length === 0 && (
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
