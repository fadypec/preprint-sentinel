/**
 * Tests for dashboard API routes.
 *
 * These tests verify request validation, response structure, and error handling.
 * Prisma and auth are mocked so tests run without a database.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Mocks — must be defined before importing route handlers
// ---------------------------------------------------------------------------

// Mock Prisma client
const mockPrisma = {
  $queryRaw: vi.fn(),
  paper: {
    count: vi.fn(),
    findMany: vi.fn(),
    groupBy: vi.fn(),
  },
  pipelineRun: {
    findFirst: vi.fn(),
  },
  pipelineSettings: {
    findUnique: vi.fn(),
    upsert: vi.fn(),
  },
};

vi.mock("@/lib/prisma", () => ({
  prisma: mockPrisma,
}));

// Mock auth guards — allow all requests in tests
vi.mock("@/lib/auth-guard", () => ({
  apiRequireAuth: vi.fn().mockResolvedValue(null),
  apiRequireAdmin: vi.fn().mockResolvedValue(null),
  csrfCheck: vi.fn().mockResolvedValue(null),
}));

// Mock rate limiter
vi.mock("@/lib/rate-limit", () => ({
  checkRateLimit: vi.fn().mockReturnValue(null),
}));

// Mock auth
vi.mock("@/lib/auth", () => ({
  auth: vi.fn().mockResolvedValue({ user: { role: "admin", status: "approved" } }),
}));

// Mock next/headers
vi.mock("next/headers", () => ({
  headers: vi.fn().mockResolvedValue(new Map()),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

// Mock search helper
vi.mock("@/lib/search", () => ({
  buildSearchQuery: vi.fn((raw: string) => {
    const cleaned = raw.replace(/[^\w\s-]/g, "").trim().split(/\s+/).filter(Boolean);
    if (cleaned.length === 0) return "";
    return cleaned.map((term: string) => `${term}:*`).join(" & ");
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Health endpoint
// ---------------------------------------------------------------------------

describe("GET /api/health", () => {
  it("returns 200 with ok status when DB is reachable and pipeline ran recently", async () => {
    const { GET } = await import("@/app/api/health/route");

    mockPrisma.$queryRaw.mockResolvedValue([{ "?column?": 1 }]);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue({
      startedAt: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
      finishedAt: new Date(Date.now() - 1 * 60 * 60 * 1000),
      errors: [],
    });

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("ok");
    expect(body.database).toBe(true);
    expect(body).toHaveProperty("checked_at");
    expect(body).toHaveProperty("hours_since_run");
  });

  it("returns 503 when DB is unreachable", async () => {
    const { GET } = await import("@/app/api/health/route");

    mockPrisma.$queryRaw.mockRejectedValue(new Error("Connection refused"));

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(503);
    expect(body.status).toBe("error");
    expect(body.database).toBe(false);
  });

  it("returns degraded when pipeline has not run recently", async () => {
    const { GET } = await import("@/app/api/health/route");

    mockPrisma.$queryRaw.mockResolvedValue([{ "?column?": 1 }]);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue({
      startedAt: new Date(Date.now() - 72 * 60 * 60 * 1000), // 72 hours ago
      finishedAt: new Date(Date.now() - 71 * 60 * 60 * 1000),
      errors: [],
    });

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("degraded");
    expect(body.database).toBe(true);
  });

  it("returns degraded when last run had errors", async () => {
    const { GET } = await import("@/app/api/health/route");

    mockPrisma.$queryRaw.mockResolvedValue([{ "?column?": 1 }]);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue({
      startedAt: new Date(Date.now() - 1 * 60 * 60 * 1000),
      finishedAt: new Date(),
      errors: ["Stage failed"],
    });

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("degraded");
    expect(body.last_run_had_errors).toBe(true);
  });

  it("returns degraded when no pipeline runs exist", async () => {
    const { GET } = await import("@/app/api/health/route");

    mockPrisma.$queryRaw.mockResolvedValue([{ "?column?": 1 }]);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue(null);

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.status).toBe("degraded");
    expect(body.last_pipeline_run).toBeNull();
    expect(body.hours_since_run).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Settings endpoint — validation
// ---------------------------------------------------------------------------

describe("PUT /api/settings", () => {
  it("rejects unknown settings keys with 400", async () => {
    const { PUT } = await import("@/app/api/settings/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest("http://localhost/api/settings", {
      method: "PUT",
      body: JSON.stringify({ unknown_key: "value" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await PUT(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("Unknown settings keys");
    expect(body.error).toContain("unknown_key");
  });

  it("rejects wrong type for numeric setting with 400", async () => {
    const { PUT } = await import("@/app/api/settings/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest("http://localhost/api/settings", {
      method: "PUT",
      body: JSON.stringify({ coarse_filter_threshold: "not_a_number" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await PUT(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("coarse_filter_threshold");
    expect(body.error).toContain("number");
  });

  it("rejects wrong type for boolean setting with 400", async () => {
    const { PUT } = await import("@/app/api/settings/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest("http://localhost/api/settings", {
      method: "PUT",
      body: JSON.stringify({ process_backlog: "yes" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await PUT(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("process_backlog");
    expect(body.error).toContain("boolean");
  });

  it("rejects array body with 400", async () => {
    const { PUT } = await import("@/app/api/settings/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest("http://localhost/api/settings", {
      method: "PUT",
      body: JSON.stringify([1, 2, 3]),
      headers: { "Content-Type": "application/json" },
    });

    const response = await PUT(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("JSON object");
  });

  it("accepts valid settings and returns updated values", async () => {
    const { PUT } = await import("@/app/api/settings/route");
    const { NextRequest } = await import("next/server");

    mockPrisma.pipelineSettings.findUnique.mockResolvedValue({
      id: 1,
      settings: { stage1_model: "old-model" },
    });
    mockPrisma.pipelineSettings.upsert.mockResolvedValue({
      id: 1,
      settings: { stage1_model: "claude-haiku-4-5-20251001" },
    });

    const request = new NextRequest("http://localhost/api/settings", {
      method: "PUT",
      body: JSON.stringify({ stage1_model: "claude-haiku-4-5-20251001" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await PUT(request);
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.stage1_model).toBe("claude-haiku-4-5-20251001");
  });
});

describe("GET /api/settings", () => {
  it("redacts secret keys in response", async () => {
    const { GET } = await import("@/app/api/settings/route");

    mockPrisma.pipelineSettings.findUnique.mockResolvedValue({
      id: 1,
      settings: {
        stage1_model: "claude-haiku-4-5-20251001",
        alert_slack_webhook: "https://hooks.slack.com/secret",
      },
    });

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.stage1_model).toBe("claude-haiku-4-5-20251001");
    // Webhook should be redacted
    expect(body.alert_slack_webhook).not.toContain("hooks.slack.com");
  });
});

// ---------------------------------------------------------------------------
// Papers endpoint — filter validation
// ---------------------------------------------------------------------------

describe("GET /api/papers", () => {
  it("returns 400 for invalid risk tier", async () => {
    const { GET } = await import("@/app/api/papers/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest(
      "http://localhost/api/papers?tier=invalid_tier",
    );

    const response = await GET(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("Invalid tier");
  });

  it("returns 400 for invalid source server", async () => {
    const { GET } = await import("@/app/api/papers/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest(
      "http://localhost/api/papers?source=fake_source",
    );

    const response = await GET(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("Invalid source");
  });

  it("returns 400 for invalid sort parameter", async () => {
    const { GET } = await import("@/app/api/papers/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest(
      "http://localhost/api/papers?sort=random_order",
    );

    const response = await GET(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("Invalid sort");
  });

  it("returns 400 for invalid dimension filter", async () => {
    const { GET } = await import("@/app/api/papers/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest(
      "http://localhost/api/papers?dim=not_a_dimension",
    );

    const response = await GET(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("Invalid dimension");
  });

  it("accepts valid filter parameters and returns 200", async () => {
    // This test verifies that valid params don't trigger a 400.
    // The queryPapers call will fail since Prisma is mocked, but the
    // route catches errors and returns 500. We just verify no 400.
    const { GET } = await import("@/app/api/papers/route");
    const { NextRequest } = await import("next/server");

    const request = new NextRequest("http://localhost/api/papers?page=1");
    const response = await GET(request);

    // Either 200 (if mocks satisfy query) or 500 (DB mock returns undefined)
    // but NOT 400 — valid params should pass validation
    expect(response.status).not.toBe(400);
  });
});

// ---------------------------------------------------------------------------
// Stats endpoint — response structure
// ---------------------------------------------------------------------------

describe("GET /api/stats", () => {
  it("returns expected KPI structure", async () => {
    const { GET } = await import("@/app/api/stats/route");

    mockPrisma.paper.count
      .mockResolvedValueOnce(42)    // papersToday
      .mockResolvedValueOnce(3)     // criticalHighToday
      .mockResolvedValueOnce(280);  // papersLastWeek
    mockPrisma.pipelineRun.findFirst.mockResolvedValue({
      startedAt: new Date(),
      finishedAt: new Date(),
      errors: [],
    });
    mockPrisma.paper.groupBy
      .mockResolvedValueOnce([
        { correspondingInstitution: "MIT", _count: { id: 5 } },
      ])
      .mockResolvedValueOnce([
        { subjectCategory: "microbiology", _count: { id: 10 } },
      ]);

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);

    // Verify KPI structure
    expect(body).toHaveProperty("kpi");
    expect(body.kpi).toHaveProperty("papersToday");
    expect(body.kpi).toHaveProperty("criticalHighToday");
    expect(body.kpi).toHaveProperty("dailyAvg");
    expect(body.kpi).toHaveProperty("trendPct");
    expect(body.kpi).toHaveProperty("lastRunStatus");
    expect(typeof body.kpi.papersToday).toBe("number");
    expect(typeof body.kpi.dailyAvg).toBe("number");

    // Verify aggregation sections
    expect(body).toHaveProperty("topInstitutions");
    expect(body).toHaveProperty("topCategories");
    expect(Array.isArray(body.topInstitutions)).toBe(true);
    expect(Array.isArray(body.topCategories)).toBe(true);
  });

  it("computes daily average from weekly count", async () => {
    const { GET } = await import("@/app/api/stats/route");

    mockPrisma.paper.count
      .mockResolvedValueOnce(10)    // papersToday
      .mockResolvedValueOnce(2)     // criticalHighToday
      .mockResolvedValueOnce(70);   // papersLastWeek
    mockPrisma.pipelineRun.findFirst.mockResolvedValue(null);
    mockPrisma.paper.groupBy
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]);

    const response = await GET();
    const body = await response.json();

    expect(body.kpi.dailyAvg).toBe(10); // 70 / 7 = 10
  });

  it("returns unknown status when no pipeline runs exist", async () => {
    const { GET } = await import("@/app/api/stats/route");

    mockPrisma.paper.count.mockResolvedValue(0);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue(null);
    mockPrisma.paper.groupBy.mockResolvedValue([]);

    const response = await GET();
    const body = await response.json();

    expect(body.kpi.lastRunStatus).toBe("unknown");
  });

  it("returns error status when last run had errors", async () => {
    const { GET } = await import("@/app/api/stats/route");

    mockPrisma.paper.count.mockResolvedValue(0);
    mockPrisma.pipelineRun.findFirst.mockResolvedValue({
      startedAt: new Date(),
      finishedAt: new Date(),
      errors: ["Something went wrong"],
    });
    mockPrisma.paper.groupBy.mockResolvedValue([]);

    const response = await GET();
    const body = await response.json();

    expect(body.kpi.lastRunStatus).toBe("error");
  });

  it("handles database errors gracefully", async () => {
    const { GET } = await import("@/app/api/stats/route");

    mockPrisma.paper.count.mockRejectedValue(new Error("DB connection lost"));

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body.error).toBe("Internal server error");
  });
});

// ---------------------------------------------------------------------------
// invalidFilters (pure function — unit tested directly)
// ---------------------------------------------------------------------------

describe("invalidFilters", () => {
  it("returns empty array for valid filters", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({ tier: "critical", sort: "date_desc" });
    expect(errors).toEqual([]);
  });

  it("accepts 'all' as a valid tier value", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({ tier: "all" });
    expect(errors).toEqual([]);
  });

  it("rejects invalid tier value", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({ tier: "super_critical" });
    expect(errors.length).toBeGreaterThan(0);
    expect(errors[0]).toContain("Invalid tier");
  });

  it("accepts comma-separated valid tiers", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({ tier: "critical,high" });
    expect(errors).toEqual([]);
  });

  it("rejects invalid dim_min values", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({ dimMin: "5" });
    expect(errors.length).toBeGreaterThan(0);
    expect(errors[0]).toContain("dim_min");
  });

  it("accepts valid dim_min values (1, 2, 3)", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    expect(invalidFilters({ dimMin: "1" })).toEqual([]);
    expect(invalidFilters({ dimMin: "2" })).toEqual([]);
    expect(invalidFilters({ dimMin: "3" })).toEqual([]);
  });

  it("returns multiple errors for multiple invalid params", async () => {
    const { invalidFilters } = await import("@/lib/queries/papers");
    const errors = invalidFilters({
      tier: "bad_tier",
      source: "bad_source",
      sort: "bad_sort",
    });
    expect(errors.length).toBe(3);
  });
});
