import { RiskTier } from "@prisma/client";

type RiskStyle = {
  badge: string;
  border: string;
  dot: string;
  label: string;
};

const styles: Record<RiskTier, RiskStyle> = {
  [RiskTier.critical]: {
    badge: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
    border: "border-l-red-500",
    dot: "bg-red-500",
    label: "CRITICAL",
  },
  [RiskTier.high]: {
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200",
    border: "border-l-orange-500",
    dot: "bg-orange-500",
    label: "HIGH",
  },
  [RiskTier.medium]: {
    badge: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-100",
    border: "border-l-yellow-500",
    dot: "bg-yellow-500",
    label: "MEDIUM",
  },
  [RiskTier.low]: {
    badge: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200",
    border: "border-l-green-500",
    dot: "bg-green-500",
    label: "LOW",
  },
  [RiskTier.refused]: {
    badge: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    border: "border-l-slate-400",
    dot: "bg-slate-400",
    label: "LLM REFUSAL",
  },
};

export function riskStyle(tier: RiskTier | null): RiskStyle {
  if (!tier) return styles[RiskTier.refused];
  return styles[tier];
}

export function dimensionColor(score: number): string {
  if (score >= 3) return "bg-red-500";
  if (score >= 2) return "bg-orange-500";
  if (score >= 1) return "bg-yellow-500";
  return "bg-slate-300 dark:bg-slate-600";
}
