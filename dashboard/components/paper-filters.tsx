"use client";

import { useQueryState, parseAsString, parseAsInteger } from "nuqs";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Search, X } from "lucide-react";

export function PaperFilters() {
  const [riskTier, setRiskTier] = useQueryState("tier", parseAsString.withDefault("all"));
  const [source, setSource] = useQueryState("source", parseAsString.withDefault("all"));
  const [status, setStatus] = useQueryState("status", parseAsString.withDefault("all"));
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));
  const [, setPage] = useQueryState("page", parseAsInteger.withDefault(1));

  const resetPage = () => setPage(1);

  const hasFilters = riskTier !== "all" || source !== "all" || status !== "all" || search !== "";

  function clearAll() {
    setRiskTier("all");
    setSource("all");
    setStatus("all");
    setSearch("");
    setPage(1);
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="search" aria-label="Filter papers">
      <Select
        value={riskTier}
        onValueChange={(v) => { setRiskTier(v); resetPage(); }}
      >
        <SelectTrigger className="w-32" aria-label="Filter by risk tier">
          <SelectValue placeholder="Risk Tier" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Tiers</SelectItem>
          <SelectItem value="critical">Critical</SelectItem>
          <SelectItem value="high">High</SelectItem>
          <SelectItem value="medium">Medium</SelectItem>
          <SelectItem value="low">Low</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={source}
        onValueChange={(v) => { setSource(v); resetPage(); }}
      >
        <SelectTrigger className="w-36" aria-label="Filter by source">
          <SelectValue placeholder="Source" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Sources</SelectItem>
          <SelectItem value="biorxiv">bioRxiv</SelectItem>
          <SelectItem value="medrxiv">medRxiv</SelectItem>
          <SelectItem value="pubmed">PubMed</SelectItem>
          <SelectItem value="europepmc">Europe PMC</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={status}
        onValueChange={(v) => { setStatus(v); resetPage(); }}
      >
        <SelectTrigger className="w-40" aria-label="Filter by review status">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Statuses</SelectItem>
          <SelectItem value="unreviewed">Unreviewed</SelectItem>
          <SelectItem value="under_review">Under Review</SelectItem>
          <SelectItem value="confirmed_concern">Confirmed Concern</SelectItem>
          <SelectItem value="false_positive">False Positive</SelectItem>
          <SelectItem value="archived">Archived</SelectItem>
        </SelectContent>
      </Select>

      <div className="relative flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
        <Input
          type="search"
          placeholder="Search papers..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          className="pl-8"
          aria-label="Search papers by title or abstract"
        />
      </div>

      {hasFilters && (
        <Button variant="ghost" size="sm" onClick={clearAll} aria-label="Clear all filters">
          <X className="mr-1 h-3 w-3" />
          Clear
        </Button>
      )}
    </div>
  );
}
