/**
 * Fetches per-country biomedical paper counts from OpenAlex for the
 * current year. Used as the denominator for normalised flag rates.
 *
 * Cached in memory for 24 hours to avoid hitting OpenAlex on every
 * page load. OpenAlex data changes slowly (weekly indexing cycle).
 *
 * GET /api/analytics/country-baseline
 * Response: { "CN": 48000, "US": 46000, "GB": 10500, ... }
 */

import { apiRequireAuth } from "@/lib/auth-guard";

// In-memory cache: { data, fetchedAt }
let cache: { data: Record<string, number>; fetchedAt: number } | null = null;
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;
  const now = Date.now();

  // Return cached data if fresh
  if (cache && now - cache.fetchedAt < CACHE_TTL_MS) {
    return Response.json(cache.data);
  }

  try {
    const year = new Date().getFullYear();
    // C86803240 = Biology concept in OpenAlex
    // Fetches article counts grouped by institution country for this year
    const url = new URL("https://api.openalex.org/works");
    url.searchParams.set("filter", `publication_year:${year},type:article,concepts.id:C86803240`);
    url.searchParams.set("group_by", "authorships.institutions.country_code");
    url.searchParams.set("per_page", "50");
    // Use polite pool email if configured
    const email = process.env.OPENALEX_EMAIL || "durc-triage@example.com";
    url.searchParams.set("mailto", email);

    const resp = await fetch(url.toString(), { next: { revalidate: 86400 } });
    if (!resp.ok) {
      console.error("OpenAlex country baseline fetch failed:", resp.status);
      return Response.json(cache?.data ?? {});
    }

    const json = await resp.json();
    const groups: { key: string; count: number }[] = json.group_by ?? [];

    // Extract 2-letter country code from OpenAlex URL format
    // "https://openalex.org/countries/CN" → "CN"
    const data: Record<string, number> = {};
    for (const g of groups) {
      const code = g.key.split("/").pop();
      if (code && code.length === 2) {
        data[code] = g.count;
      }
    }

    cache = { data, fetchedAt: now };
    return Response.json(data);
  } catch (err) {
    console.error("OpenAlex country baseline error:", err);
    // Return stale cache or empty
    return Response.json(cache?.data ?? {});
  }
}
