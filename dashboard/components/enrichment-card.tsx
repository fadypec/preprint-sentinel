import { AlertTriangle } from "lucide-react";

type OpenAlexAuthor = {
  name?: string;
  orcid?: string | null;
  institution?: string | null;
  works_count?: number | null;
  cited_by_count?: number | null;
};

type EnrichmentData = {
  openalex?: {
    cited_by_count?: number;
    topics?: { display_name: string }[];
    primary_institution?: string;
    funder_names?: string[];
    authors?: OpenAlexAuthor[];
  };
  s2?: {
    tldr?: string;
    citation_count?: number;
    first_author_h_index?: number;
  };
  orcid?: {
    orcid_id?: string;
    current_institution?: string;
    employment_history?: string[];
  };
  _meta?: {
    sources_succeeded: string[];
    sources_failed: string[];
  };
};

type Props = {
  data: EnrichmentData | null;
};

export function EnrichmentCard({ data }: Props) {
  if (!data) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No enrichment data available.
      </p>
    );
  }

  const meta = data._meta;
  const failed = meta?.sources_failed ?? [];

  return (
    <div className="space-y-3">
      {failed.length > 0 && (
        <div className="flex items-start gap-2 rounded-md bg-orange-50 p-3 text-xs text-orange-700 dark:bg-orange-900/20 dark:text-orange-300" role="alert">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>Partial enrichment — failed sources: {failed.join(", ")}</span>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {data.s2?.first_author_h_index != null && (
          <>
            <dt className="text-slate-500 dark:text-slate-400">h-index</dt>
            <dd className="text-slate-700 dark:text-slate-300">{data.s2.first_author_h_index}</dd>
          </>
        )}
        {data.openalex?.cited_by_count != null && (
          <>
            <dt className="text-slate-500 dark:text-slate-400">Citations</dt>
            <dd className="text-slate-700 dark:text-slate-300">{data.openalex.cited_by_count.toLocaleString()}</dd>
          </>
        )}
        {data.orcid?.orcid_id && (
          <>
            <dt className="text-slate-500 dark:text-slate-400">ORCID</dt>
            <dd>
              <a
                href={`https://orcid.org/${data.orcid.orcid_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline dark:text-blue-400"
              >
                {data.orcid.orcid_id}
              </a>
            </dd>
          </>
        )}
        {data.openalex?.primary_institution && (
          <>
            <dt className="text-slate-500 dark:text-slate-400">Institution</dt>
            <dd className="text-slate-700 dark:text-slate-300">{data.openalex.primary_institution}</dd>
          </>
        )}
      </dl>

      {data.openalex?.topics && data.openalex.topics.length > 0 && (
        <div>
          <span className="text-xs text-slate-500 dark:text-slate-400">Topics: </span>
          <span className="text-xs text-slate-700 dark:text-slate-300">
            {data.openalex.topics.map((t) => t.display_name).join(", ")}
          </span>
        </div>
      )}
    </div>
  );
}
