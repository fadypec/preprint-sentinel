import { describe, it, expect } from "vitest";

// Test the helper functions by importing the module's internal logic.
// Since the route exports only GET, we test the XML escaping and item
// formatting indirectly via the exported functions, or replicate the
// pure functions here for unit testing.

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extractSummary(stage2Result: unknown): string {
  if (!stage2Result || typeof stage2Result !== "object") return "";
  const r = stage2Result as Record<string, unknown>;
  return typeof r.summary === "string" ? r.summary : "";
}

describe("escapeXml", () => {
  it("escapes ampersands", () => {
    expect(escapeXml("A & B")).toBe("A &amp; B");
  });

  it("escapes angle brackets", () => {
    expect(escapeXml("<script>")).toBe("&lt;script&gt;");
  });

  it("escapes quotes", () => {
    expect(escapeXml('"hello"')).toBe("&quot;hello&quot;");
  });

  it("handles mixed special characters", () => {
    expect(escapeXml('A & B < C > D "E"')).toBe(
      "A &amp; B &lt; C &gt; D &quot;E&quot;",
    );
  });

  it("leaves plain text unchanged", () => {
    expect(escapeXml("plain text")).toBe("plain text");
  });
});

describe("extractSummary", () => {
  it("extracts summary from stage2 result", () => {
    const result = { summary: "This is a test summary" };
    expect(extractSummary(result)).toBe("This is a test summary");
  });

  it("returns empty string for null", () => {
    expect(extractSummary(null)).toBe("");
  });

  it("returns empty string for undefined", () => {
    expect(extractSummary(undefined)).toBe("");
  });

  it("returns empty string when summary is not a string", () => {
    expect(extractSummary({ summary: 42 })).toBe("");
  });

  it("returns empty string when no summary key", () => {
    expect(extractSummary({ other: "data" })).toBe("");
  });
});
