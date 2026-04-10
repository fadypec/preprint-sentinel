import { prisma } from "@/lib/prisma";
import { apiRequireAuth } from "@/lib/auth-guard";
import { ReviewStatus } from "@prisma/client";

/**
 * Export analyst feedback (confirmed_concern / false_positive papers)
 * for prompt refinement analysis.
 *
 * GET /api/feedback              — all labelled papers
 * GET /api/feedback?status=false_positive — only FPs
 * GET /api/feedback?since=2026-03-01 — labelled after date
 */
export async function GET(request: Request) {
  const denied = await apiRequireAuth();
  if (denied) return denied;

  const url = new URL(request.url);
  const statusParam = url.searchParams.get("status");
  const sinceParam = url.searchParams.get("since");

  const feedbackStatuses: ReviewStatus[] = [];
  if (statusParam === "confirmed_concern") {
    feedbackStatuses.push(ReviewStatus.confirmed_concern);
  } else if (statusParam === "false_positive") {
    feedbackStatuses.push(ReviewStatus.false_positive);
  } else {
    feedbackStatuses.push(ReviewStatus.confirmed_concern, ReviewStatus.false_positive);
  }

  const where: Record<string, unknown> = {
    reviewStatus: { in: feedbackStatuses },
  };

  if (sinceParam) {
    const sinceDate = new Date(sinceParam);
    if (!isNaN(sinceDate.getTime())) {
      where.updatedAt = { gte: sinceDate };
    }
  }

  const papers = await prisma.paper.findMany({
    where,
    orderBy: { updatedAt: "desc" },
    select: {
      id: true,
      doi: true,
      title: true,
      abstract: true,
      authors: true,
      correspondingInstitution: true,
      sourceServer: true,
      postedDate: true,
      riskTier: true,
      aggregateScore: true,
      reviewStatus: true,
      analystNotes: true,
      stage1Result: true,
      stage2Result: true,
      stage3Result: true,
      updatedAt: true,
    },
  });

  const summary = {
    confirmed_concern: papers.filter((p) => p.reviewStatus === "confirmed_concern").length,
    false_positive: papers.filter((p) => p.reviewStatus === "false_positive").length,
  };

  return Response.json({
    exported_at: new Date().toISOString(),
    total: papers.length,
    summary,
    papers: papers.map((p) => ({
      id: p.id,
      doi: p.doi,
      title: p.title,
      abstract: p.abstract,
      institution: p.correspondingInstitution,
      source: p.sourceServer,
      posted_date: p.postedDate,
      risk_tier: p.riskTier,
      aggregate_score: p.aggregateScore,
      review_status: p.reviewStatus,
      analyst_notes: p.analystNotes,
      coarse_filter_result: p.stage1Result,
      methods_analysis_result: p.stage2Result,
      adjudication_result: p.stage3Result,
      labelled_at: p.updatedAt,
    })),
  });
}
