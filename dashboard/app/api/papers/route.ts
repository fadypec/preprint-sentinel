import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma, PipelineStage, RiskTier, SourceServer, ReviewStatus } from "@prisma/client";
import { buildSearchQuery } from "@/lib/search";

const PAGE_SIZE = 20;

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10));
  const tier = params.get("tier");
  const source = params.get("source");
  const status = params.get("status");
  const search = params.get("q")?.trim();

  const where: Prisma.PaperWhereInput = {
    // Only show papers that passed the coarse filter
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
      // Full-text search via raw SQL for tsvector
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

  return Response.json({
    papers,
    total,
    page,
    pageSize: PAGE_SIZE,
    totalPages: Math.ceil(total / PAGE_SIZE),
  });
}
