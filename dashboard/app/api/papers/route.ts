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

    // Validate enum filter values -- return 400 for invalid input
    const errors = invalidFilters({ tier, source, status });
    if (errors.length > 0) {
      return Response.json({ error: errors.join("; ") }, { status: 400 });
    }

    const result = await queryPapers({ page, tier, source, status, search });

    return Response.json(result);
  } catch (err) {
    console.error("Papers API error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
