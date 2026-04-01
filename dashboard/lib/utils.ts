import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDuration(start: Date | string, end: Date | string | null): string {
  if (!end) return "Running...";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

export type DimensionEntry = { score: number; justification: string };
export type Dimensions = Record<string, DimensionEntry>;

/**
 * Safely parse the dimensions field from stage2Result.
 * It may be a JSON string or already a parsed object.
 * Handles common LLM artifacts: trailing commas, stray quotes, truncation.
 */
export function parseDimensions(raw: unknown): Dimensions {
  if (!raw) return {};
  if (typeof raw === "object" && !Array.isArray(raw)) return raw as Dimensions;
  if (typeof raw !== "string") return {};

  // Trim whitespace, then truncate after the last '}' to remove trailing junk
  let cleaned = raw.trim();
  const lastBrace = cleaned.lastIndexOf("}");
  if (lastBrace === -1) return {};
  cleaned = cleaned.slice(0, lastBrace + 1);

  // Strip trailing commas before closing braces
  cleaned = cleaned.replace(/,\s*}/g, "}");

  try {
    return JSON.parse(cleaned) as Dimensions;
  } catch {
    return {};
  }
}

const LANGUAGE_NAMES: Record<string, string> = {
  chi: "Chinese", zho: "Chinese", jpn: "Japanese", kor: "Korean",
  ger: "German", deu: "German", fre: "French", fra: "French",
  spa: "Spanish", por: "Portuguese", ita: "Italian", rus: "Russian",
  ara: "Arabic", hin: "Hindi", tur: "Turkish", pol: "Polish",
  nld: "Dutch", swe: "Swedish", dan: "Danish", nor: "Norwegian",
  fin: "Finnish", ces: "Czech", hun: "Hungarian", ron: "Romanian",
  tha: "Thai", vie: "Vietnamese", ind: "Indonesian", msa: "Malay",
  heb: "Hebrew", per: "Persian", fas: "Persian", ukr: "Ukrainian",
};

export function languageName(code: string): string {
  return LANGUAGE_NAMES[code.toLowerCase()] ?? code.toUpperCase();
}

export function sourceServerLabel(server: string): string {
  const labels: Record<string, string> = {
    biorxiv: "bioRxiv",
    medrxiv: "medRxiv",
    europepmc: "Europe PMC",
    pubmed: "PubMed",
    arxiv: "arXiv",
    research_square: "Research Square",
    chemrxiv: "ChemRxiv",
    zenodo: "Zenodo",
    ssrn: "SSRN",
  };
  return labels[server] ?? server;
}
