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
