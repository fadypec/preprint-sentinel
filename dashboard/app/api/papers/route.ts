import { NextRequest } from "next/server";
import { queryPapers, invalidFilters } from "@/lib/queries/papers";
import { apiRequireAuth } from "@/lib/auth-guard";

export async function GET(request: NextRequest) {
  const denied = await apiRequireAuth();
  if (denied) return denied;
  try {
    const params = request.nextUrl.searchParams;
    const page = parseInt(params.get("page") ?? "1", 10) || 1;
    const tier = params.get("tier");
    const source = params.get("source");
    const status = params.get("status");
    const search = params.get("q")?.trim();
    const needsReview = params.get("needs_review");
    const sort = params.get("sort");
    const dim = params.get("dim");
    const dimMin = params.get("dim_min");
    const author = params.get("author")?.trim();
    const institution = params.get("institution")?.trim();
    const hasErrors = params.get("has_errors");
    const dateFrom = params.get("date_from");
    const dateTo = params.get("date_to");
    const category = params.get("category");
    const country = params.get("country")?.trim();

    // Validate enum filter values -- return 400 for invalid input
    const errors = invalidFilters({ tier, source, status, sort, dim, dimMin });
    if (errors.length > 0) {
      return Response.json({ error: errors.join("; ") }, { status: 400 });
    }

    const result = await queryPapers({ page, tier, source, status, search, needsReview, hasErrors, sort, dim, dimMin, author, institution, dateFrom, dateTo, category, country });

    return Response.json(result);
  } catch (err) {
    console.error("Papers API error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
