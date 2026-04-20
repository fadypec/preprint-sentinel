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
const VALID_SORTS = new Set<string>([
  "date_desc", "date_asc",
  "score_desc", "score_asc"
]);
const VALID_DIMENSIONS = new Set<string>([
  "pathogen_enhancement",
  "synthesis_barrier_lowering",
  "select_agent_relevance",
  "novel_technique",
  "information_hazard",
  "defensive_framing",
]);
const VALID_DIM_MINS = new Set<number>([1, 2, 3]);

/** List columns for feed queries — excludes heavy TEXT columns (full_text_content, methods_section, original_*). */
const PAPER_LIST_COLUMNS = Prisma.raw(
  "id, doi, title, authors, corresponding_author, corresponding_institution, " +
  "abstract, source_server, posted_date, subject_category, version, " +
  "language, " +
  "full_text_url, full_text_retrieved, " +
  "enrichment_data, pipeline_stage, coarse_filter_passed, " +
  "stage1_result, stage2_result, stage3_result, " +
  "risk_tier, recommended_action, aggregate_score, " +
  "review_status, needs_manual_review, analyst_notes, " +
  "is_duplicate_of, created_at, updated_at"
);

/** All columns for detail queries (includes full text). */
const PAPER_ALL_COLUMNS = Prisma.raw(
  "id, doi, title, authors, corresponding_author, corresponding_institution, " +
  "abstract, source_server, posted_date, subject_category, version, " +
  "language, original_title, original_abstract, original_methods_section, " +
  "full_text_url, full_text_retrieved, full_text_content, methods_section, " +
  "enrichment_data, pipeline_stage, coarse_filter_passed, " +
  "stage1_result, stage2_result, stage3_result, " +
  "risk_tier, recommended_action, aggregate_score, " +
  "review_status, needs_manual_review, analyst_notes, " +
  "is_duplicate_of, created_at, updated_at"
);

/** Cached check for whether the search_vector column exists. Checked once at module load. */
let _hasSearchVector: boolean | null = null;
async function hasSearchVectorColumn(): Promise<boolean> {
  if (_hasSearchVector !== null) return _hasSearchVector;
  const colCheck = await prisma.$queryRaw<{ column_name: string }[]>`
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'papers' AND column_name = 'search_vector'
  `;
  _hasSearchVector = colCheck.length > 0;
  return _hasSearchVector;
}

/** Validate a YYYY-MM-DD date string. Returns the string if valid, undefined otherwise. */
function validDateStr(v?: string | null): string | undefined {
  if (!v) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return undefined;
  const d = new Date(v);
  if (isNaN(d.getTime())) return undefined;
  return v;
}

export type PaperQueryParams = {
  page: number;
  tier?: string | null;
  source?: string | null;
  status?: string | null;
  search?: string | null;
  needsReview?: string | null;
  hasErrors?: string | null;
  sort?: string | null;
  dim?: string | null;
  dimMin?: string | null;
  author?: string | null;
  institution?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  category?: string | null;
  country?: string | null;
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

function validSort(v?: string | null): string | undefined {
  if (!v) return "date_desc"; // default
  return VALID_SORTS.has(v) ? v : "date_desc";
}

function validDimension(v?: string | null): string | undefined {
  if (!v || v === "all") return undefined;
  return VALID_DIMENSIONS.has(v) ? v : undefined;
}

function validDimMin(v?: string | null): number | undefined {
  if (!v) return undefined;
  const n = parseInt(v, 10);
  return VALID_DIM_MINS.has(n) ? n : undefined;
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
  sort?: string | null;
  dim?: string | null;
  dimMin?: string | null;
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
  if (
    params.sort &&
    !VALID_SORTS.has(params.sort)
  ) {
    errors.push(`Invalid sort: ${params.sort}`);
  }
  if (
    params.dim &&
    params.dim !== "all" &&
    !VALID_DIMENSIONS.has(params.dim)
  ) {
    errors.push(`Invalid dimension: ${params.dim}`);
  }
  if (params.dimMin) {
    const n = parseInt(params.dimMin, 10);
    if (!VALID_DIM_MINS.has(n)) {
      errors.push(`Invalid dim_min: ${params.dimMin} (must be 1, 2, or 3)`);
    }
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
    needsManualReview: row.needs_manual_review ?? false,
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
  const needsReview = params.needsReview === "true" ? true : undefined;
  const sort = validSort(params.sort);
  const dim = validDimension(params.dim);
  const dimMin = dim ? validDimMin(params.dimMin) ?? 1 : undefined;
  const author = params.author?.trim() || undefined;
  const institution = params.institution?.trim() || undefined;
  const hasErrors = params.hasErrors === "true" ? true : undefined;
  const dateFrom = validDateStr(params.dateFrom);
  const dateTo = validDateStr(params.dateTo);
  const category = params.category?.trim() || undefined;
  const country = params.country?.trim().toUpperCase() || undefined;

  // Dimension filtering, author/institution ILIKE, full-text search,
  // date range, category, country, and error filtering all require raw SQL.
  if (search || dim || author || institution || hasErrors || dateFrom || dateTo || category || country) {
    return queryPapersRawSQL({ page, tiers, source, status, search, needsReview, hasErrors, sort: sort!, dim, dimMin, author, institution, dateFrom, dateTo, category, country });
  }

  return queryPapersPrisma({ page, tiers, source, status, needsReview, sort: sort! });
}

/** Standard Prisma query path (no full-text search). */
async function queryPapersPrisma(filters: {
  page: number;
  tiers?: RiskTier[];
  source?: SourceServer;
  status?: ReviewStatus;
  needsReview?: boolean;
  sort: string;
}): Promise<PaperQueryResult> {
  const where: Prisma.PaperWhereInput = {
    pipelineStage: { not: PipelineStage.ingested },
    coarseFilterPassed: true,
    isDuplicateOf: null,
  };

  if (filters.tiers) where.riskTier = { in: filters.tiers };
  if (filters.source) where.sourceServer = filters.source;
  if (filters.status) where.reviewStatus = filters.status;
  if (filters.needsReview) where.needsManualReview = true;

  // Build orderBy based on sort parameter
  let orderBy: Prisma.PaperOrderByWithRelationInput[];
  switch (filters.sort) {
    case "score_desc":
      orderBy = [
        { riskTier: { sort: "desc", nulls: "last" } },
        { aggregateScore: { sort: "desc", nulls: "last" } },
        { postedDate: "desc" },
      ];
      break;
    case "score_asc":
      orderBy = [
        { riskTier: { sort: "desc", nulls: "last" } },
        { aggregateScore: { sort: "asc", nulls: "first" } },
        { postedDate: "desc" },
      ];
      break;
    case "date_asc":
      orderBy = [
        { riskTier: { sort: "desc", nulls: "last" } },
        { postedDate: "asc" },
      ];
      break;
    case "date_desc":
    default:
      orderBy = [
        { riskTier: { sort: "desc", nulls: "last" } },
        { postedDate: "desc" },
      ];
  }

  const [total, totalIngested, papers] = await Promise.all([
    prisma.paper.count({ where }),
    prisma.paper.count({ where: { isDuplicateOf: null } }),
    prisma.paper.findMany({
      where,
      orderBy,
      take: PAGE_SIZE,
      skip: (filters.page - 1) * PAGE_SIZE,
      // Exclude heavy TEXT columns from list queries (multi-MB per row)
      omit: {
        fullTextContent: true,
        methodsSection: true,
        originalTitle: true,
        originalAbstract: true,
        originalMethodsSection: true,
      },
    }) as Promise<Paper[]>,
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

/** Raw SQL path — used for full-text search, dimension filtering, author/institution ILIKE, date range, category, country, and error filtering. */
async function queryPapersRawSQL(filters: {
  page: number;
  tiers?: RiskTier[];
  source?: SourceServer;
  status?: ReviewStatus;
  search?: string;
  needsReview?: boolean;
  hasErrors?: boolean;
  sort: string;
  dim?: string;
  dimMin?: number;
  author?: string;
  institution?: string;
  dateFrom?: string;
  dateTo?: string;
  category?: string;
  country?: string;
}): Promise<PaperQueryResult> {
  // Full-text search clause (optional)
  let searchClause = Prisma.empty;
  if (filters.search) {
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

    // Cached check — avoids information_schema query on every search
    if (await hasSearchVectorColumn()) {
      searchClause = Prisma.sql`AND search_vector @@ to_tsquery('english', ${tsquery})`;
    } else {
      // search_vector column doesn't exist, fall back to ILIKE search
      const searchTerms = filters.search.toLowerCase().split(/\s+/).filter(Boolean);
      if (searchTerms.length > 0) {
        const likePatterns = searchTerms.map(term => `%${term}%`);
        searchClause = Prisma.sql`AND (
          lower(title) LIKE ANY(ARRAY[${Prisma.join(likePatterns)}]) OR
          lower(abstract) LIKE ANY(ARRAY[${Prisma.join(likePatterns)}])
        )`;
      }
    }
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
  const needsReviewClause =
    filters.needsReview
      ? Prisma.sql`AND needs_manual_review = true`
      : Prisma.empty;

  // SECURITY: filters.dim is validated against VALID_DIMENSIONS whitelist — do not remove that check
  const dimClause =
    filters.dim && filters.dimMin != null
      ? Prisma.sql`AND (stage2_result->'dimensions'->${filters.dim}->>'score')::int >= ${filters.dimMin}`
      : Prisma.empty;

  // Author ILIKE clause (searches within JSONB authors array serialized as text)
  const authorClause =
    filters.author
      ? Prisma.sql`AND authors::text ILIKE ${"%" + filters.author + "%"}`
      : Prisma.empty;

  // Institution ILIKE clause
  const institutionClause =
    filters.institution
      ? Prisma.sql`AND corresponding_institution ILIKE ${"%" + filters.institution + "%"}`
      : Prisma.empty;

  // Error filter clause — papers with _error in stage results or needs_manual_review
  const errorsClause =
    filters.hasErrors
      ? Prisma.sql`AND (needs_manual_review = true OR stage2_result::text LIKE '%_error%' OR stage3_result::text LIKE '%_error%')`
      : Prisma.empty;

  // Date range clauses
  const dateFromClause =
    filters.dateFrom
      ? Prisma.sql`AND posted_date >= ${filters.dateFrom}::date`
      : Prisma.empty;
  const dateToClause =
    filters.dateTo
      ? Prisma.sql`AND posted_date <= ${filters.dateTo}::date`
      : Prisma.empty;

  // Subject category clause
  const categoryClause =
    filters.category && filters.category !== "all"
      ? Prisma.sql`AND subject_category ILIKE ${filters.category}`
      : Prisma.empty;

  // Country clause (from OpenAlex enrichment data)
  const countryClause =
    filters.country
      ? Prisma.sql`AND enrichment_data->'openalex'->'institution'->>'country_code' = ${filters.country}`
      : Prisma.empty;

  // Computed score expression: falls back to sum of dimension scores
  // when aggregate_score is NULL (matches client-side computeAggregateScore)
  const scoreExpr = Prisma.sql`COALESCE(
    aggregate_score,
    (
      COALESCE((stage2_result->'dimensions'->'pathogen_enhancement'->>'score')::int, 0) +
      COALESCE((stage2_result->'dimensions'->'synthesis_barrier_lowering'->>'score')::int, 0) +
      COALESCE((stage2_result->'dimensions'->'select_agent_relevance'->>'score')::int, 0) +
      COALESCE((stage2_result->'dimensions'->'novel_technique'->>'score')::int, 0) +
      COALESCE((stage2_result->'dimensions'->'information_hazard'->>'score')::int, 0) +
      COALESCE((stage2_result->'dimensions'->'defensive_framing'->>'score')::int, 0)
    )
  )`;

  // Build ORDER BY clause based on sort parameter
  let orderByClause: Prisma.Sql;
  switch (filters.sort) {
    case "score_desc":
      orderByClause = Prisma.sql`
        ORDER BY
          CASE risk_tier
            WHEN 'critical' THEN 4
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END DESC,
          ${scoreExpr} DESC NULLS LAST,
          posted_date DESC
      `;
      break;
    case "score_asc":
      orderByClause = Prisma.sql`
        ORDER BY
          CASE risk_tier
            WHEN 'critical' THEN 4
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END DESC,
          ${scoreExpr} ASC NULLS FIRST,
          posted_date DESC
      `;
      break;
    case "date_asc":
      orderByClause = Prisma.sql`
        ORDER BY
          CASE risk_tier
            WHEN 'critical' THEN 4
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END DESC,
          posted_date ASC
      `;
      break;
    case "date_desc":
    default:
      orderByClause = Prisma.sql`
        ORDER BY
          CASE risk_tier
            WHEN 'critical' THEN 4
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END DESC,
          posted_date DESC
      `;
      break;
  }

  // Run count, totalIngested, and data queries in parallel
  const [countResult, totalIngestedResult, rawPapers] = await Promise.all([
    prisma.$queryRaw<[{ count: bigint }]>`
      SELECT COUNT(*) as count FROM papers
      WHERE pipeline_stage != 'ingested'
        AND coarse_filter_passed = true
        AND is_duplicate_of IS NULL
        ${searchClause}
        ${tierClause}
        ${sourceClause}
        ${statusClause}
        ${needsReviewClause}
        ${dimClause}
        ${authorClause}
        ${institutionClause}
        ${errorsClause}
        ${dateFromClause}
        ${dateToClause}
        ${categoryClause}
        ${countryClause}
    `,
    prisma.$queryRaw<[{ count: bigint }]>`
      SELECT COUNT(*) as count FROM papers WHERE is_duplicate_of IS NULL
    `,
    prisma.$queryRaw<Record<string, unknown>[]>`
      SELECT ${PAPER_LIST_COLUMNS} FROM papers
      WHERE pipeline_stage != 'ingested'
        AND coarse_filter_passed = true
        AND is_duplicate_of IS NULL
        ${searchClause}
        ${tierClause}
        ${sourceClause}
        ${statusClause}
        ${needsReviewClause}
        ${dimClause}
        ${authorClause}
        ${institutionClause}
        ${errorsClause}
        ${dateFromClause}
        ${dateToClause}
        ${categoryClause}
        ${countryClause}
      ${orderByClause}
      LIMIT ${PAGE_SIZE} OFFSET ${(filters.page - 1) * PAGE_SIZE}
    `,
  ]);
  const total = Number(countResult[0].count);
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
