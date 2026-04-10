import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";

/**
 * Public feed of flagged papers for programmatic consumption.
 *
 * GET /api/feed           — JSON feed (default)
 * GET /api/feed?format=rss — RSS 2.0 XML
 * GET /api/feed?tier=critical,high — filter by risk tier
 * GET /api/feed?limit=50  — number of items (default 50, max 200)
 */
export async function GET(request: NextRequest) {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const params = request.nextUrl.searchParams;
  const format = params.get("format") ?? "json";
  const tierParam = params.get("tier");
  const limitParam = params.get("limit");

  const limit = Math.min(Math.max(parseInt(limitParam ?? "50", 10) || 50, 1), 200);

  const tierFilter = tierParam
    ? tierParam.split(",").filter((t) => ["critical", "high", "medium", "low"].includes(t))
    : undefined;

  const papers = await prisma.paper.findMany({
    where: {
      isDuplicateOf: null,
      coarseFilterPassed: true,
      pipelineStage: { not: "ingested" },
      ...(tierFilter && tierFilter.length > 0
        ? { riskTier: { in: tierFilter as ("critical" | "high" | "medium" | "low")[] } }
        : {}),
    },
    orderBy: { postedDate: "desc" },
    take: limit,
    select: {
      id: true,
      doi: true,
      title: true,
      authors: true,
      correspondingAuthor: true,
      correspondingInstitution: true,
      abstract: true,
      sourceServer: true,
      postedDate: true,
      subjectCategory: true,
      riskTier: true,
      aggregateScore: true,
      recommendedAction: true,
      stage2Result: true,
      reviewStatus: true,
      createdAt: true,
    },
  });

  if (format === "rss") {
    return new Response(buildRss(papers, request.nextUrl.origin), {
      headers: {
        "Content-Type": "application/rss+xml; charset=utf-8",
        "Cache-Control": "public, max-age=300",
      },
    });
  }

  return Response.json(
    {
      version: "1.0",
      title: "DURC Preprint Triage — Flagged Papers",
      updated: new Date().toISOString(),
      count: papers.length,
      items: papers.map(formatItem),
    },
    {
      headers: { "Cache-Control": "public, max-age=300" },
    },
  );
}

type FeedPaper = {
  id: string;
  doi: string | null;
  title: string;
  authors: unknown;
  correspondingAuthor: string | null;
  correspondingInstitution: string | null;
  abstract: string | null;
  sourceServer: string;
  postedDate: Date | string;
  subjectCategory: string | null;
  riskTier: string | null;
  aggregateScore: number | null;
  recommendedAction: string | null;
  stage2Result: unknown;
  reviewStatus: string;
  createdAt: Date | string;
};

function extractSummary(stage2Result: unknown): string {
  if (!stage2Result || typeof stage2Result !== "object") return "";
  const r = stage2Result as Record<string, unknown>;
  return typeof r.summary === "string" ? r.summary : "";
}

function formatItem(p: FeedPaper) {
  return {
    id: p.id,
    doi: p.doi,
    title: p.title,
    authors: p.authors,
    institution: p.correspondingInstitution,
    source: p.sourceServer,
    posted_date: p.postedDate,
    category: p.subjectCategory,
    risk_tier: p.riskTier,
    aggregate_score: p.aggregateScore,
    recommended_action: p.recommendedAction,
    review_status: p.reviewStatus,
    summary: extractSummary(p.stage2Result),
    link: p.doi ? `https://doi.org/${p.doi}` : null,
  };
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildRss(papers: FeedPaper[], origin: string): string {
  const items = papers
    .map((p) => {
      const link = p.doi ? `https://doi.org/${p.doi}` : `${origin}/paper/${p.id}`;
      const summary = extractSummary(p.stage2Result);
      const description = summary || (typeof p.abstract === "string" ? p.abstract.slice(0, 500) : "");
      const tier = p.riskTier ?? "unknown";
      const pubDate = new Date(p.postedDate).toUTCString();

      return `    <item>
      <title>${escapeXml(p.title)}</title>
      <link>${escapeXml(link)}</link>
      <guid isPermaLink="false">${p.id}</guid>
      <pubDate>${pubDate}</pubDate>
      <category>${escapeXml(tier)}</category>
      <description>${escapeXml(description)}</description>
    </item>`;
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>DURC Preprint Triage — Flagged Papers</title>
    <link>${origin}</link>
    <description>Papers flagged for dual-use research of concern indicators</description>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>`;
}
