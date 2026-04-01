# DURC Preprint Triage System

## Project overview

Build an AI-enabled pipeline that monitors life sciences preprint servers and published literature daily, triaging papers for dual-use research of concern (DURC) indicators. The system should reduce the volume of literature a human biosecurity analyst must review by ~99%, surfacing only papers with genuine dual-use risk signals.

This is a biosecurity tool intended for use by policy researchers, institutional biosafety committees, and oversight bodies. It is NOT a censorship tool — it is an early-warning system.

### Key design principles

- **High recall, moderate precision**: Missing a genuinely concerning paper is far worse than surfacing a false positive. The coarse filter (Stage 1) should err heavily on the side of inclusion.
- **Human-in-the-loop**: The system produces risk assessments with reasoning chains. It does NOT make decisions. Every flagged paper must be reviewed by a qualified human analyst.
- **Auditability**: Every classification decision must be logged with the full prompt, model response, and reasoning. Analysts must be able to understand _why_ a paper was flagged.
- **Cost discipline**: Target <$5K/year in API costs at steady state. Use model tiering aggressively — Haiku for bulk filtering, Sonnet for methods analysis, Opus for ambiguous adjudication.

---

## Architecture

### Pipeline stages

```
[Data Sources] → [Ingest & Dedup] → [Stage 1: Coarse Filter] → [Full-Text Retrieval] → [Stage 2: Methods Analysis] → [Stage 3: Adjudication] → [Outputs]
```

### Stage 0: Data sources

Monitor the following sources daily. Priority ordering reflects volume and relevance to DURC screening.

#### Tier 1 — Primary (must have at launch)

| Source | API | Endpoint pattern | Auth | Rate limits | Notes |
|--------|-----|-------------------|------|-------------|-------|
| **bioRxiv** | REST JSON | `https://api.biorxiv.org/details/biorxiv/{from}/{to}/{cursor}` | None | No official limit; enforce 1 req/s | Returns 100 results per page. Paginate via cursor. Covers biology preprints. Full-text XML available via their TDM S3 bucket. |
| **medRxiv** | REST JSON | `https://api.biorxiv.org/details/medrxiv/{from}/{to}/{cursor}` | None | Same as bioRxiv | Same CSHL API, different server parameter. Health sciences preprints. |
| **PubMed / E-utilities** | REST XML/JSON | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` then `efetch.fcgi` | API key (free, get from NCBI) | 10 req/s with API key, 3/s without | Covers indexed journal articles. Use for published versions of preprints + journal-only publications. Full text via PMC OA subset. |
| **Europe PMC** | REST JSON | `https://www.ebi.ac.uk/europepmc/webservices/rest/search` | None | Reasonable use | **Critical aggregator**: indexes 35 preprint servers including bioRxiv, medRxiv, Research Square, Preprints.org, SSRN, ChemRxiv, OSF Preprints, and more. Use `SRC:PPR` filter for preprints. Provides Annotations API for text-mined entities. Best single endpoint for broad preprint coverage. |

#### Tier 2 — Secondary (add after launch)

| Source | API | Notes |
|--------|-----|-------|
| **arXiv (q-bio, cs.AI+bio)** | OAI-PMH + REST (`https://export.arxiv.org/api/query`) | Quantitative biology section. Also monitor cs.AI papers with biological applications. OAI-PMH for bulk harvest, REST for targeted queries. Free, no auth. |
| **Research Square** | Crossref (DOI prefix 10.21203) | Large preprint server (~2,500 biomedical postings/month). No dedicated API — harvest via Crossref `posted-content` filter with their prefix. |
| **ChemRxiv** | Crossref (DOI prefix 10.26434) | Chemistry preprints. Relevant for synthesis routes, novel chemical agents. |
| **Zenodo** | REST JSON (`https://zenodo.org/api/records`) | General-purpose repository. Some preprints land here instead of/alongside disciplinary servers. Use `type=publication&subtype=preprint` filter. |
| **SSRN** | Crossref | Multidisciplinary. Increasingly used for life sciences. No dedicated API; harvest via Crossref. |

#### Tier 3 — Enrichment APIs (not data sources, used for context)

| API | Purpose | Auth | Cost |
|-----|---------|------|------|
| **OpenAlex** | Author/institution metadata, citation data, topic classification. 260M+ works indexed. | Free API key (polite pool) | Free. 100K calls/day limit. |
| **Semantic Scholar** | Author profiles, citation context, TLDRs, related papers. | Free (100 req/5min, higher with key) | Free |
| **Unpaywall** | Find OA full-text URLs for any DOI. | Email parameter required | Free. 100K calls/day. |
| **Crossref** | DOI metadata, publication links, funder info. | Free (polite pool with email) | Free |
| **ORCID** | Author identity resolution, institutional affiliation verification. | Public API free | Free |

### Stage 1: Ingest & Deduplicate

**Runs**: Daily cron, 06:00 UTC (after bioRxiv's daily batch).

**Process**:
1. Query each Tier 1 source for new content since last run.
2. Normalise metadata to a common schema (see below).
3. Deduplicate using a multi-signal approach:
   - **Primary**: DOI exact match (catches same paper across sources).
   - **Secondary**: Title similarity (Levenshtein ratio > 0.92) + first author surname match. Handles cases where a paper appears on both Zenodo and bioRxiv with slightly different titles.
   - **Tertiary**: For papers without DOIs (rare but possible from Zenodo/OSF), use title + author + date within ±7 days.
4. When duplicates are found, keep the record with the richest metadata (prefer bioRxiv/medRxiv records which include subject categories).
5. Store all records in the database regardless of dedup outcome — flag duplicates but retain for audit.

**Common metadata schema**:

```json
{
  "id": "uuid",
  "doi": "10.1101/...",
  "title": "...",
  "authors": [{"name": "...", "orcid": "...", "affiliation": "..."}],
  "corresponding_author": "...",
  "corresponding_institution": "...",
  "abstract": "...",
  "source_server": "biorxiv|medrxiv|europepmc|arxiv|pubmed|...",
  "posted_date": "YYYY-MM-DD",
  "subject_category": "...",
  "version": 1,
  "full_text_url": "...",
  "full_text_retrieved": false,
  "full_text_content": null,
  "pipeline_stage": "ingested",
  "stage1_result": null,
  "stage2_result": null,
  "stage3_result": null,
  "is_duplicate_of": null,
  "created_at": "...",
  "updated_at": "..."
}
```

### Stage 2: Coarse Filter (Haiku-tier)

**Model**: Claude Haiku (claude-haiku-4-5-20251001) or equivalent cheap model.

**Input**: Title + abstract only.

**Task**: Binary classification — is this paper _plausibly_ relevant to dual-use biosecurity concerns?

**Prompt strategy**:

```
You are a biosecurity screening assistant. Your task is to determine whether a scientific paper's abstract suggests it MAY be relevant to dual-use research of concern (DURC) in the biological sciences.

A paper is RELEVANT if its abstract suggests ANY of the following:
- Enhancement of pathogen transmissibility, virulence, host range, or immune evasion
- Reconstruction or synthesis of dangerous pathogens (select agents, PPPs, or novel threats)
- Novel methods for producing biological toxins or bioactive compounds with harm potential
- Techniques that could lower barriers to creating biological weapons (simplified reverse genetics, benchtop synthesis protocols, democratised access to dangerous capabilities)
- Gain-of-function research on potential pandemic pathogens
- Novel delivery mechanisms for biological agents (aerosol, vector-based, environmental release)
- Identification of novel vulnerabilities in human, animal, or plant biology that could be exploited
- Work on agents listed under the Australia Group, BWC, or national select agent regulations
- De novo protein design or directed evolution of proteins with potential toxin-like or pathogen-enhancing functions
- Dual-use research on prions, mirror-life organisms, or xenobiology
- AI/ML methods specifically applied to pathogen enhancement, toxin design, or bioweapon-relevant optimisation

A paper is NOT RELEVANT if it is:
- Standard clinical research, epidemiology, public health surveillance (unless involving enhanced pathogens)
- Drug discovery, vaccine development, or diagnostics (unless the methods themselves are dual-use)
- Basic molecular biology, structural biology, or biochemistry with no obvious dual-use application
- Ecology, environmental science, agriculture (unless involving biological control agents with crossover potential)
- Pure computational biology, bioinformatics methods papers (unless specifically applied to the above)

You MUST err on the side of flagging. If there is ANY ambiguity, flag it as RELEVANT.

Paper title: {title}
Abstract: {abstract}

Respond with ONLY a JSON object:
{
  "relevant": true|false,
  "confidence": 0.0-1.0,
  "reason": "one sentence explanation"
}
```

**Expected throughput**: ~5,000 papers/day. At Haiku pricing, ~$0.50-1.00/day.

**Expected filter rate**: ~95% discarded (confidence > 0.8 that paper is not relevant).

### Stage 3: Full-Text Retrieval

For papers passing Stage 2, retrieve full text.

**Retrieval cascade** (try in order):
1. **bioRxiv/medRxiv TDM S3 bucket**: Full-text XML in JATS format. Bulk access explicitly consented to by authors. Preferred source. URL pattern: `https://www.biorxiv.org/content/{doi}.full.xml`
2. **Europe PMC full text**: JATS XML for CC-licensed preprints. `https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/fullTextXML`
3. **PubMed Central OA**: For published articles with PMC IDs. `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmcid}`
4. **Unpaywall**: Query by DOI to find any OA copy. `https://api.unpaywall.org/v2/{doi}?email={your_email}`
5. **Direct scraping**: As last resort, scrape the preprint server HTML page. Use `rvest`-style extraction. Respect robots.txt.

**Extraction**: From JATS XML or HTML, extract the **methods section** specifically. If no clearly delineated methods section exists, extract the full text. Store both the raw content and the extracted methods section.

**Expected retrieval rate**: ~60-75% of flagged papers will yield usable full text via free/legal means.

### Stage 4: Methods Analysis (Sonnet-tier)

**Model**: Claude Sonnet (claude-sonnet-4-6) for the structured assessment.

**Input**: Methods section (or full text if methods unavailable) + abstract.

**Task**: Structured DURC risk assessment against a defined rubric.

**Prompt strategy**:

```
You are a dual-use research of concern (DURC) risk assessor with deep expertise in microbiology, virology, synthetic biology, and biosecurity policy. You are reviewing the methods section of a scientific paper that has been flagged as potentially relevant to DURC.

Assess this paper against each of the following risk dimensions. For each dimension, provide a score (0-3) and a brief justification.

## Risk dimensions

1. **Pathogen enhancement** (0-3): Does the paper describe experimental enhancement of pathogen transmissibility, virulence, host range, immune evasion, or drug resistance? Score 0 if no enhancement work. Score 1 if indirect (e.g., characterisation that could inform enhancement). Score 2 if methods could be adapted for enhancement. Score 3 if direct enhancement is described.

2. **Synthesis/reconstruction barrier lowering** (0-3): Do the methods lower technical barriers to synthesising or reconstructing dangerous pathogens? Consider: are protocols unusually detailed? Are simplified or novel techniques described that make previously difficult work accessible? Score 0-3 based on degree of barrier lowering.

3. **Select agent / PPP relevance** (0-3): Does the work involve pathogens on the WHO, Australia Group, CDC Select Agent, or ACDP Hazard Group 3/4 lists? Or potential pandemic pathogens? Score 0 if no relevant agents. Score 1 for Hazard Group 2 / non-select agents. Score 2 for HG3 / select agents. Score 3 for HG4 / PPPs / Tier 1 select agents.

4. **Novelty of dual-use technique** (0-3): Does the paper describe a genuinely novel technique, tool, or approach that has dual-use potential? Score 0 for well-established methods. Score 1 for incremental improvements. Score 2 for significant methodological advances. Score 3 for transformative new capabilities.

5. **Information hazard** (0-3): Does the paper provide specific, actionable information that could be directly misused (exact sequences, detailed protocols, step-by-step synthesis routes)? Score 0 if information is generic or already widely known. Score 3 if the paper is essentially a recipe.

6. **Defensive framing adequacy** (0-3, inverse): Does the paper adequately discuss dual-use implications, describe risk mitigation measures, or frame the work in a defensive context? Score 0 if the paper has robust dual-use discussion and risk mitigation. Score 3 if there is NO mention of dual-use risks despite clearly dual-use methods.

Paper title: {title}
Abstract: {abstract}
Methods section: {methods}

Respond with ONLY a JSON object:
{
  "dimensions": {
    "pathogen_enhancement": {"score": 0, "justification": "..."},
    "synthesis_barrier_lowering": {"score": 0, "justification": "..."},
    "select_agent_relevance": {"score": 0, "justification": "..."},
    "novel_technique": {"score": 0, "justification": "..."},
    "information_hazard": {"score": 0, "justification": "..."},
    "defensive_framing": {"score": 0, "justification": "..."}
  },
  "aggregate_score": 0,
  "risk_tier": "low|medium|high|critical",
  "summary": "2-3 sentence overall assessment",
  "key_methods_of_concern": ["list of specific methods or techniques flagged"],
  "recommended_action": "archive|monitor|review|escalate"
}
```

**Risk tier thresholds** (aggregate_score = sum of all dimensions, max 18):
- **Low** (0-4): Archive. No further action.
- **Medium** (5-8): Monitor. Include in weekly summary.
- **High** (9-13): Review. Include in daily digest. Requires analyst attention.
- **Critical** (14-18): Escalate. Immediate notification. Requires senior analyst review.

**Expected throughput**: ~150-500 papers/day. At Sonnet pricing, ~$5-8/day.

### Stage 5: Expert Adjudication (Opus-tier)

**Model**: Claude Opus (claude-opus-4-6) for nuanced contextual assessment.

**Input**: Full Stage 4 assessment + full text + enrichment data (author profiles, institutional context, funding info from OpenAlex/Semantic Scholar).

**Triggered for**: Papers scoring Medium-High or above from Stage 4 (~5-20/day).

**Task**: Contextual adjudication considering:
- Is the research group well-established in this field? (Use OpenAlex author data)
- Is the institution known for responsible dual-use research?
- Is the work funded by an agency with DURC oversight (NIH, BBSRC, Wellcome)?
- Does the work duplicate or extend previously published dual-use research?
- Is this an incremental advance in a well-governed research programme, or a concerning new direction?

**Expected cost**: ~$3-5/day at Opus pricing.

### Stage 6: Outputs

The system should produce multiple output formats.

---

## Dashboard specification

Build as a **Next.js application** with the following features.

### Core views

1. **Daily feed**: Reverse-chronological list of papers that passed Stage 2+. Each card shows:
   - Title (linked to source)
   - Authors, institution, posted date
   - Source server badge (bioRxiv, medRxiv, etc.)
   - Risk tier badge (colour-coded: green/amber/orange/red)
   - Aggregate score
   - 2-3 sentence summary from Stage 4/5
   - Expand to see full dimension scores and justifications

2. **Filtered views**:
   - Filter by risk tier, date range, source server, subject category
   - Filter by specific risk dimension (e.g., "show me all papers scoring ≥2 on information_hazard")
   - Full-text search across titles, abstracts, and assessment summaries
   - Filter by author, institution, or country

3. **Paper detail view**:
   - Full metadata
   - Complete Stage 4 and Stage 5 assessments with reasoning
   - Link to original paper
   - Methods section (if retrieved) with highlighted passages of concern
   - Author/institution context from OpenAlex
   - Related papers (by author, topic, or citation)
   - Analyst notes field (editable)
   - Status workflow: Unreviewed → Under Review → Confirmed Concern → False Positive → Archived

4. **Analytics dashboard**:
   - Papers processed per day/week/month
   - Distribution by risk tier over time
   - Top flagged institutions and research groups
   - Top flagged subject categories
   - Trend lines for specific risk dimensions
   - Pipeline health metrics (retrieval rates, API latencies, error rates)

5. **Alert configuration**:
   - Email digest (daily/weekly) with configurable risk tier threshold
   - Slack webhook integration for critical-tier papers
   - RSS feed for programmatic consumption

### Dashboard tech stack

- **Framework**: Next.js 14+ with App Router
- **Database**: PostgreSQL (via Supabase or similar) for paper records and assessments
- **Search**: Full-text search via PostgreSQL `tsvector` or Typesense if volume grows
- **Auth**: Simple auth (this is an internal tool, not public)
- **Styling**: Tailwind CSS, clean minimal design
- **Charts**: Recharts for analytics views
- **Deployment**: Vercel or similar

---

## Tech stack

### Backend pipeline

- **Language**: Python 3.11+
- **Task scheduling**: `APScheduler` or `celery` with Redis for daily cron jobs
- **HTTP client**: `httpx` (async) for API calls
- **XML parsing**: `lxml` for JATS XML full-text extraction
- **Database**: PostgreSQL with SQLAlchemy ORM
- **LLM calls**: Anthropic Python SDK (`anthropic` package)
- **Logging**: `structlog` for structured JSON logging

### Infrastructure

- **Hosting**: Single VPS (Hetzner/DigitalOcean, ~$20/month) or equivalent
- **Database**: Managed PostgreSQL (Supabase free tier is sufficient initially)
- **Cron**: systemd timers or cron on the VPS
- **Monitoring**: Simple health checks + Sentry for error tracking

---

## Cost model

| Component | Monthly cost |
|-----------|-------------|
| Haiku (Stage 2, ~5K papers/day) | ~$15-30 |
| Sonnet (Stage 4, ~300 papers/day) | ~$150-240 |
| Opus (Stage 5, ~15 papers/day) | ~$90-150 |
| VPS hosting | ~$20 |
| Database (Supabase) | $0-25 |
| Domain + misc | ~$5 |
| **Total** | **~$280-470/month ($3,400-5,600/year)** |

---

## Deduplication strategy — detailed

Cross-posting is common. A single paper may appear on bioRxiv AND be indexed in Europe PMC AND later appear in PubMed once published. The dedup system must handle:

1. **Same preprint, multiple indexes**: bioRxiv paper also in Europe PMC. Same DOI. Trivial — DOI match.
2. **Preprint → published version**: bioRxiv preprint later published in Nature. Different DOI. Use bioRxiv's `/pubs/` endpoint which tracks preprint-to-publication links, or Europe PMC's preprint-journal linking. Also check Crossref `is-preprint-of` relation.
3. **Cross-posted to multiple servers**: Paper on both Zenodo and bioRxiv. May have different DOIs. Use title+author similarity matching.
4. **Updated versions**: bioRxiv v1 → v2 → v3. Same DOI, different content. Track version numbers. Re-screen if methods section has changed substantially.

For cases 2-4, maintain a `paper_group` table linking related records. Display the latest/richest version to analysts but preserve the full history.

---

## DURC rubric — detailed guidance for LLM prompts

The following categories define what the system is screening for. These are drawn from:
- US NSABB DURC Policy (2024 revision)
- UK ACDP guidelines on dual-use research
- Australian Group common control lists
- WHO Laboratory Biosafety Manual (4th edition)
- Fink Report categories of dual-use experiments

### High-priority signals (always flag)

- Gain-of-function experiments on influenza, coronaviruses, or other PPPs
- Reverse genetics systems for HG3/4 pathogens
- Directed evolution or de novo design of toxins or virulence factors
- Enhanced aerosol transmissibility of respiratory pathogens
- Immune evasion mutations mapped with explicit residue-level detail
- Reconstruction of historical or extinct pathogens (1918 flu, smallpox-adjacent)
- Simplified protocols for producing select agents or toxins
- AI/ML-guided optimisation of pathogen fitness or toxin potency
- Mirror-life organism creation or mirror-chirality biological systems
- Benchtop synthesis of dangerous biological agents from commercial reagents

### Medium-priority signals (flag for review)

- Broad-spectrum antibiotic/antiviral resistance mechanisms
- Novel drug delivery systems with dual-use potential (nanoparticles, aerosol)
- Gene drive technology in wild populations
- Large-scale environmental release of engineered organisms
- Characterisation of novel zoonotic viruses with pandemic potential
- Detailed vulnerability mapping of agricultural systems to biological attack
- Dual-use enabling technologies (cell-free systems, microfluidic pathogen production)

### Context that reduces concern

- Work conducted under established DURC oversight (declared DURC review, IBC approval cited)
- Published by groups with track records in biosafety/biosecurity
- Funded by agencies with DURC review processes (NIH, BARDA, DTRA)
- Defensive framing with explicit risk mitigation discussion
- Methods section references established biosafety protocols (BSL-3/4 containment described)

---

## File structure

```
durc-triage/
├── CLAUDE.md                    # This file
├── README.md                    # User-facing documentation
├── pyproject.toml               # Python dependencies
├── .env.example                 # Environment variables template
│
├── pipeline/                    # Backend pipeline
│   ├── __init__.py
│   ├── config.py                # Configuration and env vars
│   ├── models.py                # SQLAlchemy models
│   ├── db.py                    # Database connection
│   │
│   ├── ingest/                  # Stage 0-1: Data ingestion
│   │   ├── __init__.py
│   │   ├── biorxiv.py           # bioRxiv/medRxiv API client
│   │   ├── europepmc.py         # Europe PMC API client
│   │   ├── pubmed.py            # PubMed E-utilities client
│   │   ├── arxiv.py             # arXiv API client
│   │   ├── crossref.py          # Crossref API client (for Research Square, ChemRxiv, SSRN)
│   │   ├── zenodo.py            # Zenodo API client
│   │   └── dedup.py             # Deduplication logic
│   │
│   ├── fulltext/                # Stage 3: Full-text retrieval
│   │   ├── __init__.py
│   │   ├── retriever.py         # Orchestrates retrieval cascade
│   │   ├── jats_parser.py       # JATS XML methods section extraction
│   │   ├── html_parser.py       # HTML fallback extraction
│   │   └── unpaywall.py         # Unpaywall API client
│   │
│   ├── triage/                  # Stages 2, 4, 5: LLM classification
│   │   ├── __init__.py
│   │   ├── coarse_filter.py     # Stage 2: Haiku abstract screening
│   │   ├── methods_analysis.py  # Stage 4: Sonnet methods assessment
│   │   ├── adjudication.py      # Stage 5: Opus contextual review
│   │   └── prompts.py           # All prompt templates (centralised)
│   │
│   ├── enrichment/              # Enrichment API clients
│   │   ├── __init__.py
│   │   ├── openalex.py          # OpenAlex author/institution lookup
│   │   ├── semantic_scholar.py  # Semantic Scholar author profiles
│   │   └── orcid.py             # ORCID identity resolution
│   │
│   ├── orchestrator.py          # Main pipeline orchestration
│   └── scheduler.py             # Cron job scheduling
│
├── dashboard/                   # Next.js frontend
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx             # Daily feed view
│   │   ├── paper/[id]/page.tsx  # Paper detail view
│   │   ├── analytics/page.tsx   # Analytics dashboard
│   │   ├── settings/page.tsx    # Alert configuration
│   │   └── api/                 # API routes
│   │       ├── papers/route.ts
│   │       ├── stats/route.ts
│   │       └── alerts/route.ts
│   ├── components/
│   │   ├── PaperCard.tsx
│   │   ├── RiskBadge.tsx
│   │   ├── DimensionScores.tsx
│   │   ├── FilterBar.tsx
│   │   ├── AnalyticsCharts.tsx
│   │   └── AlertConfig.tsx
│   └── lib/
│       ├── db.ts
│       └── types.ts
│
├── scripts/
│   ├── seed_db.py               # Initial database setup
│   ├── backfill.py              # Backfill historical papers
│   └── test_pipeline.py         # End-to-end pipeline test
│
└── tests/
    ├── test_ingest.py
    ├── test_dedup.py
    ├── test_fulltext.py
    ├── test_triage.py
    └── fixtures/                # Sample papers for testing
        ├── sample_biorxiv.json
        ├── sample_jats.xml
        └── sample_methods.txt
```

---

## Implementation order

Build in this order. Each phase should be functional and testable before proceeding.

### Phase 1: Core pipeline (backend only)
1. Database models and migrations
2. bioRxiv + medRxiv ingest clients
3. Deduplication logic
4. Stage 2 coarse filter (Haiku)
5. Full-text retrieval (bioRxiv XML + Unpaywall)
6. Stage 4 methods analysis (Sonnet)
7. Orchestrator + scheduler
8. **Test**: Run on 1 week of historical data and inspect results

### Phase 2: Enrichment + adjudication
1. Europe PMC ingest client
2. OpenAlex enrichment
3. Stage 5 adjudication (Opus)
4. PubMed ingest client
5. **Test**: Run on 1 month of historical data

### Phase 3: Dashboard
1. Basic Next.js scaffold with database connection
2. Daily feed view with paper cards
3. Paper detail view with full assessment
4. Filter and search functionality
5. Analytics charts
6. Alert configuration (email + Slack)

### Phase 4: Expansion
1. arXiv, Research Square, ChemRxiv, Zenodo ingest
2. Semantic Scholar + ORCID enrichment
3. Analyst feedback loop (confirmed/false positive feeds back to prompt refinement)
4. RSS/JSON API for external consumption
5. Version tracking and re-screening

---

## Environment variables

```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# Database
DATABASE_URL=postgresql://user:pass@host:5432/durc_triage

# APIs (all free, email-based auth)
NCBI_API_KEY=...                    # From https://www.ncbi.nlm.nih.gov/account/settings/
UNPAYWALL_EMAIL=your@email.com      # Used as auth parameter
OPENALEX_EMAIL=your@email.com       # For polite pool access
SEMANTIC_SCHOLAR_API_KEY=...        # Optional, for higher rate limits

# Alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SMTP_HOST=...
SMTP_FROM=alerts@yourdomain.com
ALERT_RECIPIENTS=analyst1@org.com,analyst2@org.com

# Pipeline config
DAILY_RUN_HOUR=6                    # UTC hour for daily pipeline run
STAGE1_MODEL=claude-haiku-4-5-20251001
STAGE2_MODEL=claude-sonnet-4-6
STAGE3_MODEL=claude-opus-4-6
COARSE_FILTER_THRESHOLD=0.8         # Confidence above which paper is discarded
```

---

## Testing strategy

### Unit tests
- Each ingest client: mock API responses, verify correct parsing
- Dedup: test all four dedup scenarios with fixture data
- JATS parser: verify methods section extraction from sample XMLs
- Triage prompts: verify JSON output parsing handles malformed responses

### Integration tests
- End-to-end: ingest 10 known papers (mix of clearly benign + known DURC-relevant), verify correct triage outcomes
- Include known DURC cases as ground truth:
  - Fouchier H5N1 airborne transmission (2012) — should score Critical
  - Ron Fink BoNT sequence optimisation — should score High
  - A standard epidemiology paper — should score Low and be filtered at Stage 2
  - A vaccine development paper using reverse genetics — should score Medium (methods are dual-use but context is defensive)

### Prompt regression tests
- Maintain a fixture set of 50+ paper abstracts with expected Stage 2 outcomes
- Run after any prompt modification to check for regressions
- Track precision/recall over time

---

## Important notes

- **Rate limiting**: Implement exponential backoff on all API clients. bioRxiv's API can be slow during peak hours. Europe PMC occasionally returns 503s. PubMed will throttle without an API key.
- **JATS XML parsing**: Methods sections are inconsistent across preprint servers. Look for `<sec sec-type="methods">`, `<sec sec-type="materials|methods">`, or heading text matching "Methods", "Materials and Methods", "Experimental Procedures". Fall back to full text if no methods section found.
- **Prompt versioning**: Store the prompt version used for each assessment alongside the result. When prompts are updated, consider re-running recent assessments to check for regression.
- **Legal/ethical**: All data sources used are open access or explicitly permit text mining. bioRxiv TDM access is author-consented. Europe PMC content is CC-licensed where full text is available. This system analyses publicly available research outputs — it does not access restricted content.
- **Responsible disclosure**: If the system flags a paper that appears to represent a genuine and immediate biosecurity threat, the operating organisation should have a pre-agreed escalation pathway. This is a policy decision, not a technical one. Document it separately.
