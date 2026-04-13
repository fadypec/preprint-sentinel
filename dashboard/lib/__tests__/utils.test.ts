import { describe, it, expect } from "vitest";
import {
  formatDate,
  formatDuration,
  formatCost,
  parseDimensions,
  computeAggregateScore,
  languageName,
  sourceServerLabel,
} from "../utils";

describe("formatDate", () => {
  it("formats a Date object", () => {
    const result = formatDate(new Date("2026-03-15"));
    expect(result).toContain("Mar");
    expect(result).toContain("2026");
  });

  it("formats a date string", () => {
    const result = formatDate("2026-03-15");
    expect(result).toContain("2026");
  });
});

describe("formatDuration", () => {
  it("returns seconds for short durations", () => {
    const start = "2026-03-15T10:00:00Z";
    const end = "2026-03-15T10:00:45Z";
    expect(formatDuration(start, end)).toBe("45s");
  });

  it("returns minutes and seconds for longer durations", () => {
    const start = "2026-03-15T10:00:00Z";
    const end = "2026-03-15T10:02:30Z";
    expect(formatDuration(start, end)).toBe("2m 30s");
  });

  it("returns Running... when end is null", () => {
    expect(formatDuration("2026-03-15T10:00:00Z", null)).toBe("Running...");
  });
});

describe("formatCost", () => {
  it("formats to two decimal places", () => {
    expect(formatCost(1.5)).toBe("$1.50");
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(123.456)).toBe("$123.46");
  });
});

describe("parseDimensions", () => {
  it("returns empty object for null/undefined", () => {
    expect(parseDimensions(null)).toEqual({});
    expect(parseDimensions(undefined)).toEqual({});
  });

  it("returns object as-is if already parsed", () => {
    const dims = { pathogen_enhancement: { score: 2, justification: "test" } };
    expect(parseDimensions(dims)).toEqual(dims);
  });

  it("parses a valid JSON string", () => {
    const json =
      '{"pathogen_enhancement": {"score": 1, "justification": "low"}}';
    const result = parseDimensions(json);
    expect(result.pathogen_enhancement.score).toBe(1);
  });

  it("handles trailing commas in JSON", () => {
    const json = '{"key": {"score": 1, "justification": "test",}}';
    const result = parseDimensions(json);
    expect(result.key.score).toBe(1);
  });

  it("returns empty object for invalid JSON", () => {
    expect(parseDimensions("not json at all")).toEqual({});
  });

  it("returns empty object for arrays", () => {
    expect(parseDimensions([1, 2, 3])).toEqual({});
  });

  it("handles truncated JSON with trailing junk", () => {
    const json = '{"key": {"score": 2, "justification": "ok"}} extra stuff';
    const result = parseDimensions(json);
    expect(result.key.score).toBe(2);
  });
});

describe("languageName", () => {
  it("maps known codes", () => {
    expect(languageName("chi")).toBe("Chinese");
    expect(languageName("jpn")).toBe("Japanese");
    expect(languageName("spa")).toBe("Spanish");
  });

  it("uppercases unknown codes", () => {
    expect(languageName("xyz")).toBe("XYZ");
  });

  it("is case-insensitive", () => {
    expect(languageName("CHI")).toBe("Chinese");
  });
});

describe("computeAggregateScore", () => {
  it("sums dimension scores", () => {
    const dims = {
      a: { score: 2, justification: "" },
      b: { score: 3, justification: "" },
      c: { score: 1, justification: "" },
    };
    expect(computeAggregateScore(dims)).toBe(6);
  });

  it("returns null for empty dimensions", () => {
    expect(computeAggregateScore({})).toBeNull();
  });
});

describe("sourceServerLabel", () => {
  it("returns human-readable labels for all sources", () => {
    expect(sourceServerLabel("biorxiv")).toBe("bioRxiv");
    expect(sourceServerLabel("medrxiv")).toBe("medRxiv");
    expect(sourceServerLabel("europepmc")).toBe("Europe PMC");
    expect(sourceServerLabel("pubmed")).toBe("PubMed");
    expect(sourceServerLabel("arxiv")).toBe("arXiv");
    expect(sourceServerLabel("research_square")).toBe("Research Square");
    expect(sourceServerLabel("chemrxiv")).toBe("ChemRxiv");
    expect(sourceServerLabel("zenodo")).toBe("Zenodo");
    expect(sourceServerLabel("ssrn")).toBe("SSRN");
  });

  it("returns raw string for unknown servers", () => {
    expect(sourceServerLabel("unknown")).toBe("unknown");
  });
});
