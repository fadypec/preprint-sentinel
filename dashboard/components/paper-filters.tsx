import { cn } from "@/lib/utils";

const TIER_OPTIONS = [
  {
    value: "critical",
    label: "Critical",
    active:
      "bg-red-600 text-white border-red-600 dark:bg-red-700 dark:border-red-700",
    inactive:
      "border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/30",
  },
  {
    value: "high",
    label: "High",
    active:
      "bg-orange-500 text-white border-orange-500 dark:bg-orange-600 dark:border-orange-600",
    inactive:
      "border-orange-300 text-orange-700 hover:bg-orange-50 dark:border-orange-800 dark:text-orange-400 dark:hover:bg-orange-900/30",
  },
  {
    value: "medium",
    label: "Medium",
    active:
      "bg-yellow-500 text-white border-yellow-500 dark:bg-yellow-600 dark:border-yellow-600",
    inactive:
      "border-yellow-300 text-yellow-700 hover:bg-yellow-50 dark:border-yellow-800 dark:text-yellow-400 dark:hover:bg-yellow-900/30",
  },
  {
    value: "low",
    label: "Low",
    active:
      "bg-green-600 text-white border-green-600 dark:bg-green-700 dark:border-green-700",
    inactive:
      "border-green-300 text-green-700 hover:bg-green-50 dark:border-green-800 dark:text-green-400 dark:hover:bg-green-900/30",
  },
  {
    value: "refused",
    label: "LLM Refusal",
    active:
      "bg-slate-600 text-white border-slate-600 dark:bg-slate-700 dark:border-slate-700",
    inactive:
      "border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800/30",
  },
] as const;

const selectClasses =
  "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50";

type PaperFiltersProps = {
  tier: string;
  source: string;
  status: string;
  q: string;
  needsReview: string;
  sort: string;
  dim: string;
  dimMin: string;
  author: string;
  institution: string;
  hasErrors: string;
  dateFrom: string;
  dateTo: string;
  category: string;
  country: string;
};

/** Build a clean URL with only non-default filter params. */
function buildUrl(filters: {
  tier: string;
  source: string;
  status: string;
  q: string;
  needsReview: string;
  hasErrors: string;
  sort: string;
  dim: string;
  author: string;
  institution: string;
  dimMin: string;
  dateFrom: string;
  dateTo: string;
  category: string;
  country: string;
}): string {
  const p = new URLSearchParams();
  if (filters.tier && filters.tier !== "all") p.set("tier", filters.tier);
  if (filters.source && filters.source !== "all")
    p.set("source", filters.source);
  if (filters.status && filters.status !== "all")
    p.set("status", filters.status);
  if (filters.q) p.set("q", filters.q);
  if (filters.needsReview === "true") p.set("needs_review", "true");
  if (filters.sort && filters.sort !== "date_desc") p.set("sort", filters.sort);
  if (filters.dim && filters.dim !== "all") p.set("dim", filters.dim);
  if (filters.dim && filters.dim !== "all" && filters.dimMin && filters.dimMin !== "1") p.set("dim_min", filters.dimMin);
  if (filters.author) p.set("author", filters.author);
  if (filters.institution) p.set("institution", filters.institution);
  if (filters.hasErrors === "true") p.set("has_errors", "true");
  if (filters.dateFrom) p.set("date_from", filters.dateFrom);
  if (filters.dateTo) p.set("date_to", filters.dateTo);
  if (filters.category && filters.category !== "all") p.set("category", filters.category);
  if (filters.country) p.set("country", filters.country);
  const qs = p.toString();
  return qs ? `/?${qs}` : "/";
}

/**
 * Server component — no "use client".
 *
 * Tier chips are plain <a> tags with server-computed hrefs.
 * They navigate via standard HTML links — zero JavaScript dependency.
 *
 * Dropdowns + search live in a <form method="GET">.
 * An inline <script> auto-submits on dropdown change (runs during HTML
 * parse, independent of React hydration). Falls back to the Go button
 * if JS never loads.
 */
export function PaperFilters({ tier, source, status, q, needsReview, hasErrors, sort, dim, dimMin, author, institution, dateFrom, dateTo, category, country }: PaperFiltersProps) {
  const selectedTiers = new Set(
    !tier || tier === "all" ? [] : tier.split(","),
  );

  /** Compute the href that toggles a single tier on/off. */
  function tierHref(value: string): string {
    const updated = new Set(selectedTiers);
    if (updated.has(value)) updated.delete(value);
    else updated.add(value);
    return buildUrl({
      tier: updated.size === 0 ? "all" : [...updated].join(","),
      source,
      status,
      q,
      needsReview,
      hasErrors,
      sort,
      dim,
      dimMin,
      author,
      institution,
      dateFrom,
      dateTo,
      category,
      country,
    });
  }

  const hasFilters =
    selectedTiers.size > 0 ||
    (source !== "all" && source !== "") ||
    (status !== "all" && status !== "") ||
    q !== "" ||
    needsReview === "true" ||
    hasErrors === "true" ||
    (sort !== "date_desc" && sort !== "") ||
    (dim !== "all" && dim !== "") ||
    author !== "" ||
    institution !== "" ||
    dateFrom !== "" ||
    dateTo !== "" ||
    (category !== "all" && category !== "") ||
    country !== "";

  const tierValue =
    selectedTiers.size > 0 ? [...selectedTiers].join(",") : "";

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      role="search"
      aria-label="Filter papers"
    >
      {/* Tier multi-select chips — plain <a> links, work without JS */}
      <div
        className="flex items-center gap-1"
        role="group"
        aria-label="Risk tier filters"
      >
        {TIER_OPTIONS.map((opt) => {
          const isActive = selectedTiers.has(opt.value);
          return (
            <a
              key={opt.value}
              href={tierHref(opt.value)}
              role="button"
              aria-pressed={isActive}
              className={cn(
                "rounded-md border px-3 py-2 min-h-[44px] text-xs font-medium no-underline transition-colors",
                isActive ? opt.active : opt.inactive,
              )}
            >
              {opt.label}
            </a>
          );
        })}
      </div>

      {/* Needs Manual Review toggle — plain <a> link like tier chips */}
      <a
        href={buildUrl({
          tier,
          source,
          status,
          q,
          needsReview: needsReview === "true" ? "" : "true",
          hasErrors,
          sort,
          dim,
          dimMin,
          author,
          institution,
          dateFrom,
          dateTo,
          category,
          country,
        })}
        role="button"
        aria-pressed={needsReview === "true"}
        className={cn(
          "rounded-md border px-2.5 py-1 text-xs font-medium no-underline transition-colors",
          needsReview === "true"
            ? "bg-amber-500 text-white border-amber-500 dark:bg-amber-600 dark:border-amber-600"
            : "border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-800 dark:text-amber-400 dark:hover:bg-amber-900/30",
        )}
      >
        Needs Review
      </a>

      {/* Has Errors toggle — plain <a> link */}
      <a
        href={buildUrl({
          tier,
          source,
          status,
          q,
          needsReview,
          hasErrors: hasErrors === "true" ? "" : "true",
          sort,
          dim,
          dimMin,
          author,
          institution,
          dateFrom,
          dateTo,
          category,
          country,
        })}
        role="button"
        aria-pressed={hasErrors === "true"}
        className={cn(
          "rounded-md border px-2.5 py-1 text-xs font-medium no-underline transition-colors",
          hasErrors === "true"
            ? "bg-red-500 text-white border-red-500 dark:bg-red-600 dark:border-red-600"
            : "border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/30",
        )}
      >
        Has Errors
      </a>

      {/* Source / Status / Search — HTML form, no React hydration needed */}
      <form
        method="GET"
        action="/"
        className="contents"
        data-filter-form=""
      >
        {/* Preserve chip-based selections when form submits */}
        {tierValue && (
          <input type="hidden" name="tier" value={tierValue} />
        )}
        {needsReview === "true" && (
          <input type="hidden" name="needs_review" value="true" />
        )}
        {hasErrors === "true" && (
          <input type="hidden" name="has_errors" value="true" />
        )}

        <label htmlFor="filter-date-from" className="sr-only">From date</label>
        <input
          id="filter-date-from"
          type="date"
          name="date_from"
          defaultValue={dateFrom}
          aria-label="Filter from date"
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
          data-auto-submit=""
        />

        <label htmlFor="filter-date-to" className="sr-only">To date</label>
        <input
          id="filter-date-to"
          type="date"
          name="date_to"
          defaultValue={dateTo}
          aria-label="Filter to date"
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
          data-auto-submit=""
        />

        <label htmlFor="filter-category" className="sr-only">Filter by subject category</label>
        <select
          id="filter-category"
          name="category"
          defaultValue={category || "all"}
          aria-label="Filter by subject category"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="all">All Categories</option>
          <option value="microbiology">Microbiology</option>
          <option value="bioinformatics">Bioinformatics</option>
          <option value="neuroscience">Neuroscience</option>
          <option value="genetics">Genetics</option>
          <option value="immunology">Immunology</option>
          <option value="cell biology">Cell Biology</option>
          <option value="biochemistry">Biochemistry</option>
          <option value="molecular biology">Molecular Biology</option>
          <option value="genomics">Genomics</option>
          <option value="synthetic biology">Synthetic Biology</option>
          <option value="biophysics">Biophysics</option>
          <option value="pathology">Pathology</option>
          <option value="pharmacology and toxicology">Pharmacology</option>
          <option value="epidemiology">Epidemiology</option>
          <option value="evolutionary biology">Evolutionary Biology</option>
        </select>

        <label htmlFor="filter-country" className="sr-only">Filter by country code</label>
        <input
          id="filter-country"
          type="text"
          name="country"
          defaultValue={country}
          placeholder="Country..."
          aria-label="Filter by country code (e.g. US, GB, CN)"
          maxLength={2}
          className="h-8 w-20 rounded-lg border border-input bg-transparent px-2.5 text-sm uppercase outline-none transition-colors placeholder:text-muted-foreground placeholder:normal-case focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
        />

        <label htmlFor="filter-author" className="sr-only">Filter by author</label>
        <input
          id="filter-author"
          type="text"
          name="author"
          defaultValue={author}
          placeholder="Author..."
          aria-label="Filter by author name"
          className="h-8 w-28 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
        />

        <label htmlFor="filter-institution" className="sr-only">Filter by institution</label>
        <input
          id="filter-institution"
          type="text"
          name="institution"
          defaultValue={institution}
          placeholder="Institution..."
          aria-label="Filter by institution"
          className="h-8 w-32 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
        />

        <label htmlFor="filter-source" className="sr-only">Filter by source</label>
        <select
          id="filter-source"
          name="source"
          defaultValue={source || "all"}
          aria-label="Filter by source"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="all">All Sources</option>
          <option value="biorxiv">bioRxiv</option>
          <option value="medrxiv">medRxiv</option>
          <option value="pubmed">PubMed</option>
          <option value="europepmc">Europe PMC</option>
          <option value="arxiv">arXiv</option>
          <option value="research_square">Research Square</option>
          <option value="chemrxiv">ChemRxiv</option>
          <option value="zenodo">Zenodo</option>
          <option value="ssrn">SSRN</option>
        </select>

        <label htmlFor="filter-status" className="sr-only">Filter by review status</label>
        <select
          id="filter-status"
          name="status"
          defaultValue={status || "all"}
          aria-label="Filter by review status"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="all">All Statuses</option>
          <option value="unreviewed">Unreviewed</option>
          <option value="under_review">Under Review</option>
          <option value="confirmed_concern">Confirmed Concern</option>
          <option value="false_positive">False Positive</option>
          <option value="archived">Archived</option>
        </select>

        <label htmlFor="filter-sort" className="sr-only">Sort order</label>
        <select
          id="filter-sort"
          name="sort"
          defaultValue={sort || "date_desc"}
          aria-label="Sort order"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="date_desc">Date (Newest)</option>
          <option value="date_asc">Date (Oldest)</option>
          <option value="score_desc">Score (High→Low)</option>
          <option value="score_asc">Score (Low→High)</option>
        </select>

        <label htmlFor="filter-dim" className="sr-only">Filter by risk dimension</label>
        <select
          id="filter-dim"
          name="dim"
          defaultValue={dim || "all"}
          aria-label="Filter by risk dimension"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="all">All Dimensions</option>
          <option value="pathogen_enhancement">Pathogen Enhancement</option>
          <option value="synthesis_barrier_lowering">Synthesis Barriers</option>
          <option value="select_agent_relevance">Select Agent</option>
          <option value="novel_technique">Novel Technique</option>
          <option value="information_hazard">Information Hazard</option>
          <option value="defensive_framing">Defensive Framing</option>
        </select>

        <label htmlFor="filter-dim-min" className="sr-only">Minimum dimension score</label>
        <select
          id="filter-dim-min"
          name="dim_min"
          defaultValue={dimMin || "1"}
          aria-label="Minimum dimension score"
          className={selectClasses}
          data-auto-submit=""
        >
          <option value="1">≥ 1</option>
          <option value="2">≥ 2</option>
          <option value="3">= 3</option>
        </select>

        <div className="relative flex-1">
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search papers..."
            aria-label="Search papers by title or abstract"
            className="h-8 w-full rounded-lg border border-input bg-transparent pl-8 pr-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30 dark:hover:bg-input/50"
          />
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>

        <button
          type="submit"
          aria-label="Apply filters"
          className="inline-flex h-8 items-center rounded-lg border border-input bg-transparent px-2.5 text-sm transition-colors hover:bg-muted dark:bg-input/30 dark:hover:bg-input/50"
        >
          Go
        </button>
      </form>

      {hasFilters && (
        // eslint-disable-next-line @next/next/no-html-link-for-pages -- intentional: plain <a> for server-side navigation
        <a
          href="/"
          className="inline-flex h-7 items-center gap-1 rounded-lg px-2.5 text-[0.8rem] font-medium transition-colors hover:bg-muted hover:text-foreground"
        >
          Clear
        </a>
      )}

      {/*
        External script for two enhancements (loaded from public/,
        CSP-compliant — no inline script needed):
        1. Auto-submit form when a dropdown changes
        2. Strip default/empty values from URL on submit
      */}
      <script src="/filter-form.js" defer />
    </div>
  );
}
