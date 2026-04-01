import { prisma } from "@/lib/prisma";
import {
  PipelineStage,
  Prisma,
  RiskTier,
  SourceServer,
  ReviewStatus,
} from "@prisma/client";
import type { Paper } from "@prisma/client";
import { buildSearchQuery } from "@/lib/search";

const PAGE_SIZE = 20;

// Valid enum values for filter validation
const VALID_TIERS = new Set<string>(Object.values(RiskTier));
const VALID_SOURCES = new Set<string>(Object.values(SourceServer));
const VALID_STATUSES = new Set<string>(Object.values(ReviewStatus));

export type PaperQueryParams = {
  page: number;
  tier?: string | null;
  source?: string | null;
  status?: string | null;
  search?: string | null;
};

export type PaperQueryResult = {
  papers: Paper[];
  total: number;
  totalIngested: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

/**
 * Validate and normalize filter values against known enums.
 * Returns the value if valid, or undefined if invalid/empty/"all".
 */
function validTiers(v?: string | null): RiskTier[] | undefined {
  if (!v || v === "all") return undefined;
  const tiers = v.split(",").filter((t) => VALID_TIERS.has(t)) as RiskTier[];
  return tiers.length > 0 ? tiers : undefined;
}

function validSource(v?: string | null): SourceServer | undefined {
  if (!v || v === "all") return undefined;
  return VALID_SOURCES.has(v) ? (v as SourceServer) : undefined;
}

function validStatus(v?: string | null): ReviewStatus | undefined {
  if (!v || v === "all") return undefined;
  return VALID_STATUSES.has(v) ? (v as ReviewStatus) : undefined;
}

/**
 * Check whether any filter values are invalid (not just empty/"all", but
 * actually present and not matching a known enum). Used by the API route
 * to return 400 for bad input.
 */
export function invalidFilters(params: {
  tier?: string | null;
  source?: string | null;
  status?: string | null;
}): string[] {
  const errors: string[] = [];
  if (params.tier && params.tier !== "all") {
    const invalid = params.tier
      .split(",")
      .filter((t) => !VALID_TIERS.has(t));
    if (invalid.length > 0) {
      errors.push(`Invalid tier(s): ${invalid.join(", ")}`);
    }
  }
  if (
    params.source &&
    params.source !== "all" &&
    !VALID_SOURCES.has(params.source)
  ) {
    errors.push(`Invalid source: ${params.source}`);
  }
  if (
    params.status &&
    params.status !== "all" &&
    !VALID_STATUSES.has(params.status)
  ) {
    errors.push(`Invalid status: ${params.status}`);
  }
  return errors;
}

/**
 * Map a raw SQL row (snake_case) to the Prisma Paper shape (camelCase).
 */
function mapRawToPaper(row: Record<string, unknown>): Paper {
  return {
    id: row.id,
    doi: row.doi ?? null,
    title: row.title,
    authors: row.authors ?? null,
    correspondingAuthor: row.corresponding_author ?? null,
    correspondingInstitution: row.corresponding_institution ?? null,
    abstract: row.abstract ?? null,
    sourceServer: row.source_server,
    postedDate: row.posted_date,
    subjectCategory: row.subject_category ?? null,
    version: row.version,
    language: row.language ?? null,
    originalTitle: row.original_title ?? null,
    originalAbstract: row.original_abstract ?? null,
    originalMethodsSection: row.original_methods_section ?? null,
    fullTextUrl: row.full_text_url ?? null,
    fullTextRetrieved: row.full_text_retrieved,
    fullTextContent: row.full_text_content ?? null,
    methodsSection: row.methods_section ?? null,
    enrichmentData: row.enrichment_data ?? null,
    pipelineStage: row.pipeline_stage,
    coarseFilterPassed: row.coarse_filter_passed ?? null,
    stage1Result: row.stage1_result ?? null,
    stage2Result: row.stage2_result ?? null,
    stage3Result: row.stage3_result ?? null,
    riskTier: row.risk_tier ?? null,
    recommendedAction: row.recommended_action ?? null,
    aggregateScore: row.aggregate_score ?? null,
    reviewStatus: row.review_status,
    analystNotes: row.analyst_notes ?? null,
    isDuplicateOf: row.is_duplicate_of ?? null,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  } as Paper;
}

/**
 * Shared paper query logic used by both the server component (page.tsx)
 * and the API route (route.ts).
 *
 * For non-search queries, uses Prisma's findMany (returns camelCase).
 * For full-text search, uses raw SQL with snake_case-to-camelCase mapping.
 */
export async function queryPapers(
  params: PaperQueryParams,
): Promise<PaperQueryResult> {
  const page = Math.max(1, Number.isFinite(params.page) ? params.page : 1);
  const tiers = validTiers(params.tier);
  const source = validSource(params.source);
  const status = validStatus(params.status);
  const search = params.search?.trim() || undefined;

  if (search) {
    return queryPapersFullText({ page, tiers, source, status, search });
  }

  return queryPapersPrisma({ page, tiers, source, status });
}

/** Standard Prisma query path (no full-text search). */
async function queryPapersPrisma(filters: {
  page: number;
  tiers?: RiskTier[];
  source?: SourceServer;
  status?: ReviewStatus;
}): Promise<PaperQueryResult> {
  const where: Prisma.PaperWhereInput = {
    pipelineStage: { not: PipelineStage.ingested },
    coarseFilterPassed: true,
    isDuplicateOf: null,
  };

  if (filters.tiers) where.riskTier = { in: filters.tiers };
  if (filters.source) where.sourceServer = filters.source;
  if (filters.status) where.reviewStatus = filters.status;

  const [total, totalIngested, papers] = await Promise.all([
    prisma.paper.count({ where }),
    prisma.paper.count({ where: { isDuplicateOf: null } }),
    prisma.paper.findMany({
      where,
      orderBy: [
        { riskTier: { sort: "desc", nulls: "last" } },
        { postedDate: "desc" },
      ],
      take: PAGE_SIZE,
      skip: (filters.page - 1) * PAGE_SIZE,
    }),
  ]);

  return {
    papers,
    total,
    totalIngested,
    page: filters.page,
    pageSize: PAGE_SIZE,
    totalPages: Math.ceil(total / PAGE_SIZE),
  };
}

/** Raw SQL path for full-text search via tsvector. */
async function queryPapersFullText(filters: {
  page: number;
  tiers?: RiskTier[];
  source?: SourceServer;
  status?: ReviewStatus;
  search: string;
}): Promise<PaperQueryResult> {
  const tsquery = buildSearchQuery(filters.search);
  if (!tsquery) {
    return {
      papers: [],
      total: 0,
      totalIngested: 0,
      page: filters.page,
      pageSize: PAGE_SIZE,
      totalPages: 0,
    };
  }

  const tierClause =
    filters.tiers
      ? Prisma.sql`AND risk_tier::text IN (${Prisma.join(filters.tiers)})`
      : Prisma.empty;
  const sourceClause =
    filters.source
      ? Prisma.sql`AND source_server = ${filters.source}::source_server`
      : Prisma.empty;
  const statusClause =
    filters.status
      ? Prisma.sql`AND review_status = ${filters.status}::review_status`
      : Prisma.empty;

  const countResult = await prisma.$queryRaw<[{ count: bigint }]>`
    SELECT COUNT(*) as count FROM papers
    WHERE search_vector @@ to_tsquery('english', ${tsquery})
      AND pipeline_stage != 'ingested'
      AND coarse_filter_passed = true
      AND is_duplicate_of IS NULL
      ${tierClause}
      ${sourceClause}
      ${statusClause}
  `;
  const total = Number(countResult[0].count);

  const rawPapers = await prisma.$queryRaw<Record<string, unknown>[]>`
    SELECT * FROM papers
    WHERE search_vector @@ to_tsquery('english', ${tsquery})
      AND pipeline_stage != 'ingested'
      AND coarse_filter_passed = true
      AND is_duplicate_of IS NULL
      ${tierClause}
      ${sourceClause}
      ${statusClause}
    ORDER BY ts_rank(search_vector, to_tsquery('english', ${tsquery})) DESC
    LIMIT ${PAGE_SIZE} OFFSET ${(filters.page - 1) * PAGE_SIZE}
  `;

  const totalIngestedResult = await prisma.$queryRaw<[{ count: bigint }]>`
    SELECT COUNT(*) as count FROM papers WHERE is_duplicate_of IS NULL
  `;
  const totalIngested = Number(totalIngestedResult[0].count);

  const papers = rawPapers.map(mapRawToPaper);

  return {
    papers,
    total,
    totalIngested,
    page: filters.page,
    pageSize: PAGE_SIZE,
    totalPages: Math.ceil(total / PAGE_SIZE),
  };
}
