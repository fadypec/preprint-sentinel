import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { Badge } from "@/components/ui/badge";
import { RiskPanel } from "@/components/risk-panel";
import { EnrichmentCard } from "@/components/enrichment-card";
import { MethodsViewer } from "@/components/methods-viewer";
import { AnalystNotes } from "@/components/analyst-notes";
import { AuditTrail } from "@/components/audit-trail";
import { riskStyle } from "@/lib/risk-colors";
import { cn, formatDate, sourceServerLabel, languageName } from "@/lib/utils";
import { ArrowLeft } from "lucide-react";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function PaperDetailPage({ params }: Props) {
  const { id } = await params;
  const paper = await prisma.paper.findUnique({
    where: { id },
    include: {
      assessmentLogs: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!paper) notFound();

  const style = riskStyle(paper.riskTier);
  const isTranslated = paper.language != null && paper.language !== "eng" && paper.originalTitle != null;
  const stage2 = paper.stage2Result as {
    summary?: string;
    key_methods_of_concern?: string[];
  } | null;
  const stage3 = paper.stage3Result as {
    summary?: string;
    institutional_context?: string;
    durc_oversight_indicators?: string[];
    adjustment_reasoning?: string;
  } | null;

  type AuthorEntry = { name?: string };
  type OpenAlexAuthor = { name?: string; orcid?: string | null };
  const authorList = Array.isArray(paper.authors)
    ? (paper.authors as unknown as AuthorEntry[])
    : null;

  // Extract per-author ORCIDs from OpenAlex enrichment data
  const enrichment = paper.enrichmentData as {
    openalex?: { authors?: OpenAlexAuthor[] };
  } | null;
  const oaAuthors = enrichment?.openalex?.authors ?? [];

  // Build a name→ORCID map from OpenAlex (normalise to lowercase for matching)
  const orcidMap = new Map<string, string>();
  for (const oa of oaAuthors) {
    if (oa.name && oa.orcid) {
      orcidMap.set(oa.name.toLowerCase(), oa.orcid);
    }
  }

  // Merge: for each paper author, try to find an ORCID match
  type AuthorWithOrcid = { name: string; orcid: string | null };
  const authorsWithOrcids: AuthorWithOrcid[] = authorList
    ? authorList.map((a) => {
        const name = a.name ?? "Unknown";
        // Try exact match, then check if OpenAlex name contains the paper author name
        let orcid = orcidMap.get(name.toLowerCase()) ?? null;
        if (!orcid) {
          for (const [oaName, oaOrcid] of orcidMap) {
            if (oaName.includes(name.split(",")[0].toLowerCase())) {
              orcid = oaOrcid;
              break;
            }
          }
        }
        return { name, orcid };
      })
    : oaAuthors
        .filter((a) => a.name)
        .map((a) => ({ name: a.name!, orcid: a.orcid ?? null }));

  return (
    <div>
      {/* Header with back button */}
      <div className="mb-6 flex items-start gap-3">
        <Link
          href="/"
          aria-label="Back to feed"
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-sm transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {paper.title}
            {isTranslated && (
              <span className="ml-2 inline-flex rounded bg-blue-100 px-1.5 py-0.5 align-middle text-xs font-normal text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                AI translated from {languageName(paper.language!)}
              </span>
            )}
          </h1>
          <div className="mt-1 flex items-center gap-2">
            <Badge className={cn(style.badge)}>{style.label}</Badge>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Score: {paper.aggregateScore ?? 0}/18
            </span>
          </div>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex gap-6">
        {/* Left column -- scrollable content */}
        <div className="min-w-0 space-y-6" style={{ flex: "7" }}>
          {/* Metadata */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Paper Metadata
            </h2>
            <div className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
              <div>
                <span className="text-slate-500 dark:text-slate-400">Authors: </span>
                {authorsWithOrcids.length > 0 ? (
                  <span>
                    {authorsWithOrcids.map((a, i) => (
                      <span key={i}>
                        {i > 0 && ", "}
                        {a.name}
                        {a.orcid && (
                          <>
                            {" "}
                            <a
                              href={`https://orcid.org/${a.orcid}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-0.5 rounded bg-green-50 px-1 py-0.5 text-[10px] font-medium text-green-700 no-underline hover:bg-green-100 dark:bg-green-900/30 dark:text-green-400 dark:hover:bg-green-900/50"
                              title={`ORCID: ${a.orcid}`}
                            >
                              ORCID
                            </a>
                          </>
                        )}
                      </span>
                    ))}
                  </span>
                ) : (
                  paper.correspondingAuthor ?? "Unknown"
                )}
              </div>
              {paper.correspondingInstitution && (
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Institution: </span>
                  {paper.correspondingInstitution}
                </div>
              )}
              <div>
                <span className="text-slate-500 dark:text-slate-400">Source: </span>
                {sourceServerLabel(paper.sourceServer)}
                {paper.doi && (
                  <>
                    {" "}&middot;{" "}
                    <a
                      href={`https://doi.org/${paper.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 underline dark:text-blue-400"
                    >
                      {paper.doi}
                    </a>
                  </>
                )}
              </div>
              <div>
                <span className="text-slate-500 dark:text-slate-400">Posted: </span>
                {formatDate(paper.postedDate)}
              </div>
            </div>
          </section>

          {/* AI Summary */}
          {(stage3?.summary || stage2?.summary) && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                AI Assessment Summary
              </h2>
              <div className="rounded-md bg-slate-100 p-4 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {stage3?.summary ?? stage2?.summary}
              </div>
            </section>
          )}

          {/* Key Methods of Concern */}
          {stage2?.key_methods_of_concern && stage2.key_methods_of_concern.length > 0 && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Key Methods of Concern
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {stage2.key_methods_of_concern.map((method) => (
                  <Badge
                    key={method}
                    variant="outline"
                    className="border-red-300 text-red-700 dark:border-red-700 dark:text-red-300"
                  >
                    {method}
                  </Badge>
                ))}
              </div>
            </section>
          )}

          {/* Adjudication Context */}
          {stage3?.institutional_context && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Adjudication Context
              </h2>
              <div className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
                <p>{stage3.institutional_context}</p>
                {stage3.durc_oversight_indicators &&
                  stage3.durc_oversight_indicators.length > 0 && (
                    <div>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        DURC Oversight Indicators:{" "}
                      </span>
                      {stage3.durc_oversight_indicators.join(", ")}
                    </div>
                  )}
                {stage3.adjustment_reasoning && (
                  <div>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      Reasoning:{" "}
                    </span>
                    {stage3.adjustment_reasoning}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Enrichment */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Author &amp; Institution Context
            </h2>
            <EnrichmentCard data={paper.enrichmentData as Record<string, unknown> | null} />
          </section>

          {/* Methods Section */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Methods Section
            </h2>
            <MethodsViewer methods={paper.methodsSection} />
          </section>

          {/* Analyst Notes */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Analyst Notes
            </h2>
            <AnalystNotes paperId={paper.id} initialNotes={paper.analystNotes} />
          </section>

          {/* Audit Trail */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Audit Trail
            </h2>
            <AuditTrail logs={paper.assessmentLogs} />
          </section>
        </div>

        {/* Right column -- sticky risk panel */}
        <div className="w-72 shrink-0" style={{ flex: "3" }}>
          <RiskPanel paper={paper} />
        </div>
      </div>
    </div>
  );
}
