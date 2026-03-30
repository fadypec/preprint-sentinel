# Phase 2 SP3: Enrichment, Adjudication & Orchestrator — Design Spec

## Goal

Add author/institution enrichment from three external APIs (OpenAlex, Semantic Scholar, ORCID), implement Stage 5 Opus adjudication with configurable trigger thresholds, and build the daily pipeline orchestrator that ties all stages together into a single invocable function.

## Architecture

SP3 completes the pipeline backend. After SP3, the system can run end-to-end as `python -m pipeline.orchestrator` — ingesting papers, filtering, retrieving full text, analysing methods, enriching metadata, and adjudicating high-risk papers.

The orchestrator has two layers: a pure async `run_daily_pipeline()` function (testable, no dependencies) and an APScheduler wrapper that runs it on a configurable cron schedule. The scheduler runs as a long-lived process alongside the dashboard, enabling the dashboard to control the schedule (change time, trigger manual runs, pause/resume) without requiring shell access to the server.

```
Papers at METHODS_ANALYSED
  → enricher fetches OpenAlex + Semantic Scholar + ORCID
  → stores merged enrichment_data on Paper
  → filter by adjudication_min_tier config
  → adjudication sends qualifying papers to Opus
  → stores stage3_result, may adjust risk_tier/recommended_action
  → pipeline_stage = ADJUDICATED
```

## Components

### 1. OpenAlex Client (`pipeline/enrichment/openalex.py`)

Async client for the OpenAlex API (`https://api.openalex.org`). Follows the same async context manager pattern as all other clients.

**Purpose:** Author/institution metadata, topic classification, citation counts.

**API endpoints used:**
- `GET /works?filter=doi:{doi}` — look up a paper by DOI to get OpenAlex work ID, cited_by_count, topics, and authorships
- Author data comes embedded in the works response (authorships array contains institution data, ORCID, author position)

**What we extract per paper:**
```python
{
    "openalex_work_id": "W1234567890",
    "cited_by_count": 42,
    "topics": [{"name": "Virology", "score": 0.95}, ...],
    "authors": [
        {
            "name": "Jane Smith",
            "openalex_id": "A1234",
            "orcid": "0000-0001-...",
            "institution": "MIT",
            "institution_country": "US",
            "institution_type": "education",
            "works_count": 150,
            "cited_by_count": 3200,
        },
        ...
    ],
    "primary_institution": "MIT",
    "primary_institution_country": "US",
    "funder_names": ["NIH", "DARPA"],
}
```

**Auth:** `openalex_email` setting (already in config) passed as `mailto` parameter for polite pool access.

**Rate limiting:** `openalex_request_delay` — add to config, default 0.1s. OpenAlex allows 100K calls/day; at ~20 papers/day reaching adjudication we're well within limits.

**Retry:** Exponential backoff on 429/503/timeout, same pattern as other clients. Max 3 retries.

### 2. Semantic Scholar Client (`pipeline/enrichment/semantic_scholar.py`)

Async client for the Semantic Scholar Academic Graph API (`https://api.semanticscholar.org/graph/v1`).

**Purpose:** Author h-index, paper TLDRs, citation context.

**API endpoints used:**
- `GET /paper/DOI:{doi}?fields=title,tldr,citationCount,influentialCitationCount,authors` — look up paper by DOI
- Author details come embedded via the `authors.authorId` field; we use `GET /author/{authorId}?fields=name,hIndex,citationCount,paperCount` for the first/corresponding author only (to stay within rate limits)

**What we extract per paper:**
```python
{
    "s2_paper_id": "abc123...",
    "tldr": "This paper describes...",
    "citation_count": 15,
    "influential_citation_count": 3,
    "first_author_h_index": 25,
    "first_author_paper_count": 80,
    "first_author_citation_count": 4500,
}
```

**Auth:** `semantic_scholar_api_key` setting (already in config, SecretStr). Passed as `x-api-key` header. Without key: 100 requests per 5 minutes. With key: higher limits.

**Rate limiting:** `semantic_scholar_request_delay` — add to config, default 1.0s (conservative, accommodates the no-key rate limit).

**Retry:** Same pattern. Max 3 retries.

### 3. ORCID Client (`pipeline/enrichment/orcid.py`)

Async client for the ORCID Public API (`https://pub.orcid.org/v3.0`).

**Purpose:** Author identity verification and institutional affiliation confirmation.

**API endpoints used:**
- `GET /v3.0/search?q=family-name:{surname}+AND+given-names:{given}` — find ORCID ID by name
- `GET /v3.0/{orcid}/record` — get employment history, education

We only query ORCID for the corresponding author (or first author if no corresponding author is identified). This keeps requests minimal.

**What we extract:**
```python
{
    "orcid_id": "0000-0001-2345-6789",
    "current_institution": "MIT",
    "employment_history": ["MIT (2020-present)", "Stanford (2015-2020)"],
    "education": ["PhD, Harvard (2015)"],
}
```

**Auth:** Public API, no key needed. Requires `Accept: application/json` header.

**Rate limiting:** `orcid_request_delay` — add to config, default 1.0s. ORCID public API has no published limit but recommends reasonable use.

**Retry:** Same pattern. Max 3 retries.

**Fallback:** If the ORCID is already known from OpenAlex data (many OpenAlex author records include ORCIDs), skip the name search and go directly to the record lookup.

### 4. Enricher (`pipeline/enrichment/enricher.py`)

Orchestrates all three enrichment sources for a single paper.

**Interface:**
```python
@dataclass(frozen=True)
class EnrichmentResult:
    data: dict               # Merged enrichment data from all sources
    sources_succeeded: list[str]  # e.g. ["openalex", "semantic_scholar"]
    sources_failed: list[str]     # e.g. ["orcid"]
    partial: bool            # True if any source failed

async def enrich_paper(paper: Paper, settings) -> EnrichmentResult:
    """Fetch enrichment data from all configured sources."""
```

**Behaviour:**
- Calls all three clients sequentially (not parallel — respects rate limits and keeps error handling simple).
- Each source wrapped in try/except. If a source fails, it's recorded in `sources_failed` and the others proceed.
- Merges results into a nested dict keyed by source: `{"openalex": {...}, "s2": {...}, "orcid": {...}}`. Each source's data uses the schema shown in its section above.
- The `partial` flag is `True` if any source failed.

**Paper update:** The orchestrator calls `enrich_paper`, then stores the result:
```python
paper.enrichment_data = {
    **result.data,
    "_meta": {
        "sources_succeeded": result.sources_succeeded,
        "sources_failed": result.sources_failed,
        "fetched_at": datetime.utcnow().isoformat(),
    },
}
```

No separate enrichment log table — the `_meta` key within `enrichment_data` tracks what succeeded/failed and when.

### 5. Adjudication (`pipeline/triage/adjudication.py`)

Stage 5: Opus contextual review. Follows the same pattern as `coarse_filter.py` and `methods_analysis.py`.

**Trigger:** Configurable via `adjudication_min_tier` setting. Default `"high"` — only papers with `risk_tier` of HIGH or CRITICAL get adjudicated. The tier ordering is: low < medium < high < critical.

**Input to Opus:** Stage 4 assessment (stage2_result) + abstract + methods section (if available) + enrichment data + partial enrichment flag.

**Prompt additions to `prompts.py`:**
- `ADJUDICATION_VERSION = "v1.0"`
- `ADJUDICATION_SYSTEM_PROMPT` — instructs Opus to consider:
  - Is the research group well-established in this field? (Use author citation counts, h-index, institution)
  - Is the institution known for responsible dual-use research?
  - Is the work funded by an agency with DURC oversight? (Use funder data from OpenAlex)
  - Does the work duplicate or extend previously published dual-use research?
  - Is this incremental in a well-governed programme, or a concerning new direction?
  - If enrichment is partial, note which sources were unavailable and how that limits confidence
- `ADJUDICATE_PAPER_TOOL` — tool schema:

```python
{
    "name": "adjudicate_paper",
    "input_schema": {
        "type": "object",
        "properties": {
            "adjusted_risk_tier": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"]
            },
            "adjusted_action": {
                "type": "string",
                "enum": ["archive", "monitor", "review", "escalate"]
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in this adjudication, reduced when enrichment is partial"
            },
            "partial_enrichment": {
                "type": "boolean",
                "description": "True if enrichment data was incomplete"
            },
            "missing_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Enrichment sources that failed"
            },
            "institutional_context": {
                "type": "string",
                "description": "Assessment of institutional/author credibility and oversight context"
            },
            "durc_oversight_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Evidence of DURC oversight (IBC approval, DURC review, biosafety protocols)"
            },
            "adjustment_reasoning": {
                "type": "string",
                "description": "Why the risk tier was adjusted (or confirmed)"
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence contextual assessment"
            }
        },
        "required": [
            "adjusted_risk_tier", "adjusted_action", "confidence",
            "partial_enrichment", "missing_sources",
            "institutional_context", "durc_oversight_indicators",
            "adjustment_reasoning", "summary"
        ]
    }
}
```

**User message format:** `format_adjudication_message(title, abstract, methods, stage2_result, enrichment_data, sources_failed)` — includes all context in a structured format.

**Result handling:**
- `paper.stage3_result = tool_input`
- `paper.risk_tier = adjusted_risk_tier` (Opus may upgrade or downgrade)
- `paper.recommended_action = adjusted_action`
- `paper.pipeline_stage = PipelineStage.ADJUDICATED`
- `AssessmentLog` with `stage="adjudication"`, same audit pattern as other stages.

**Sync mode only.** Batch mode is not needed — adjudication processes ~5-20 papers/day. No `use_batch` parameter.

### 6. Schema Changes (`pipeline/models.py`)

Add one column to Paper:
```python
enrichment_data: Mapped[dict | None] = mapped_column(PlatformJSON)
```

Add to the "Full text" column group (below `methods_section`). This stores the merged enrichment data from all three sources plus the `_sources_succeeded` / `_sources_failed` metadata.

**Migration:** Create `alembic/versions/` migration script (or if Alembic is not set up yet, create a standalone `scripts/migrate_add_enrichment.py` that runs `ALTER TABLE papers ADD COLUMN enrichment_data JSONB`). The column is nullable with no default, so the migration is non-destructive.

### 7. Config Additions (`pipeline/config.py`)

```python
# Enrichment
openalex_request_delay: float = 0.1
semantic_scholar_request_delay: float = 1.0
orcid_request_delay: float = 1.0

# Adjudication
adjudication_min_tier: str = "high"  # "low", "medium", "high", "critical"
```

`openalex_email`, `semantic_scholar_api_key`, `daily_run_hour` already exist in config.

**New dependency:** `apscheduler>=4.0` (or `>=3.10` as fallback). Add to `pyproject.toml`.

### 8. Orchestrator (`pipeline/orchestrator.py`)

**Interface:**
```python
@dataclass
class PipelineRunStats:
    started_at: datetime
    finished_at: datetime | None
    papers_ingested: int
    papers_after_dedup: int
    papers_coarse_passed: int
    papers_fulltext_retrieved: int
    papers_methods_analysed: int
    papers_enriched: int
    papers_adjudicated: int
    errors: list[str]
    total_cost_usd: float

async def run_daily_pipeline(settings: Settings | None = None) -> PipelineRunStats:
    """Run the complete daily triage pipeline."""
```

**Stage sequence:**
1. **Ingest**: Create clients for bioRxiv, medRxiv, Europe PMC, PubMed. Iterate each, insert papers into DB.
2. **Dedup**: For each new paper, run `check_duplicate` against existing records. Record duplicates.
3. **Coarse filter**: Query papers at `INGESTED` stage (non-duplicates). Run `run_coarse_filter`.
4. **Full-text retrieval**: For each paper that passed coarse filter, run `retrieve_full_text`.
5. **Methods analysis**: Query papers at `FULLTEXT_RETRIEVED`. Run `run_methods_analysis`.
6. **Enrichment**: Query papers at `METHODS_ANALYSED` where `risk_tier >= adjudication_min_tier`. Run `enrich_paper` for each.
7. **Adjudication**: Run `run_adjudication` on the enriched papers.
8. **Auto-advance**: Papers at `METHODS_ANALYSED` that are below the adjudication threshold (e.g., Low/Medium when threshold is "high") are advanced to `ADJUDICATED` without Opus review. This ensures `ADJUDICATED` is the terminal pipeline stage for all papers that complete the pipeline. Their `stage3_result` is set to `None` and `risk_tier`/`recommended_action` remain as set by Stage 4.

Each stage is wrapped in try/except so a failure in one stage logs the error but doesn't prevent later stages from running on papers already at the right stage from previous runs.

**Date range:** By default, processes papers from the last 2 days (`date.today() - timedelta(days=2)` to `date.today()`). The 2-day window handles papers posted late in the day or API delays. Duplicate detection prevents reprocessing.

**`__main__` entry point:**
```python
# pipeline/__main__.py
if __name__ == "__main__":
    import asyncio
    from pipeline.orchestrator import run_daily_pipeline
    stats = asyncio.run(run_daily_pipeline())
    print(stats)
```

Invoked as: `python -m pipeline` or `uv run python -m pipeline` for a one-shot run. For continuous scheduled operation, use the scheduler (below).

### 9. Scheduler (`pipeline/scheduler.py`)

APScheduler-based wrapper that runs the orchestrator on a configurable cron schedule. This is the long-lived process that keeps the pipeline running daily without manual intervention.

**Dependency:** `apscheduler>=4.0` (APScheduler v4 is async-native and supports asyncio natively).

Note: APScheduler v4 is a major rewrite from v3. It uses `AsyncScheduler` with `CronTrigger` and is designed for async applications. If v4 is not stable at implementation time, fall back to `apscheduler>=3.10` with `AsyncIOScheduler`.

**Interface:**
```python
class PipelineScheduler:
    """Manages scheduled and on-demand pipeline runs."""

    def __init__(self, settings: Settings) -> None: ...

    async def start(self) -> None:
        """Start the scheduler with the configured daily cron."""

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""

    async def trigger_run(self) -> PipelineRunStats:
        """Trigger an immediate pipeline run (for dashboard 'Run Now' button)."""

    async def update_schedule(self, hour: int, minute: int = 0) -> None:
        """Change the daily run time (for dashboard schedule config)."""

    async def pause(self) -> None:
        """Pause scheduled runs (manual runs still allowed)."""

    async def resume(self) -> None:
        """Resume scheduled runs."""

    def get_status(self) -> dict:
        """Return scheduler state for the dashboard.

        Returns:
            {
                "running": bool,
                "paused": bool,
                "next_run_time": "ISO datetime or null",
                "last_run_time": "ISO datetime or null",
                "last_run_stats": PipelineRunStats or null,
            }
        """
```

**Config:** Uses the existing `daily_run_hour: int = 6` setting for the initial schedule. The dashboard can change this at runtime via `update_schedule()`.

**State tracking:** The scheduler stores `last_run_stats` (the most recent `PipelineRunStats`) in memory. The dashboard reads this to show pipeline health. For persistence across restarts, the stats are also logged to the database (a simple `pipeline_runs` table — see schema changes below).

**Process model:** The scheduler runs in the same process as the dashboard backend. When the dashboard is deployed (Phase 3), the Next.js frontend calls a Python API backend (FastAPI or similar) that hosts both the scheduler and the API endpoints. For SP3, the scheduler can run standalone:

```python
# pipeline/__main__.py with --schedule flag
if __name__ == "__main__":
    import asyncio
    import sys
    if "--schedule" in sys.argv:
        from pipeline.scheduler import PipelineScheduler
        from pipeline.config import get_settings
        scheduler = PipelineScheduler(get_settings())
        asyncio.run(scheduler.start())  # Blocks forever, runs daily
    else:
        from pipeline.orchestrator import run_daily_pipeline
        stats = asyncio.run(run_daily_pipeline())
        print(stats)
```

### 10. Schema Addition: Pipeline Run Log

Add a `PipelineRun` model to track run history (used by the dashboard to show pipeline health):

```python
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    papers_ingested: Mapped[int] = mapped_column(Integer, default=0)
    papers_after_dedup: Mapped[int] = mapped_column(Integer, default=0)
    papers_coarse_passed: Mapped[int] = mapped_column(Integer, default=0)
    papers_fulltext_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    papers_methods_analysed: Mapped[int] = mapped_column(Integer, default=0)
    papers_enriched: Mapped[int] = mapped_column(Integer, default=0)
    papers_adjudicated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(PlatformJSON)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trigger: Mapped[str] = mapped_column(String(50))  # "scheduled" | "manual"
```

The orchestrator writes a `PipelineRun` row at the start (with `started_at` and `trigger`) and updates it at the end (with stats and `finished_at`). This gives the dashboard a complete run history independent of the scheduler's in-memory state.

### 11. Dashboard Configuration Note

All configurable settings introduced in SP3 (and retroactively, SP2) must have corresponding UI elements in the dashboard when Phase 3 is implemented:

**Pipeline schedule (from scheduler):**
- Daily run time — time picker, calls `update_schedule()`
- Pause/resume toggle — calls `pause()` / `resume()`
- "Run Now" button — calls `trigger_run()`
- Pipeline status display — shows `get_status()` (next run, last run, health)
- Run history table — reads from `pipeline_runs` table

**Pipeline tuning:**
- `adjudication_min_tier` — dropdown or radio button
- `use_batch_api` — toggle switch
- `coarse_filter_threshold` — slider (0.0-1.0)
- `pubmed_query_mode` — dropdown ("all" / "mesh_filtered")
- Rate limit delays — numeric inputs
- Model selection (`stage1_model`, `stage2_model`, `stage3_model`) — dropdowns

This note will be saved to project memory and referenced during Phase 3 dashboard design.

## Testing Strategy

### Enrichment clients (per client)
- Mock HTTP responses with realistic data, verify correct field extraction.
- Test 404/missing data returns None gracefully.
- Test retry on 429/503.
- Test timeout handling.

### Enricher
- Test all three sources succeed — merged data has all prefixed keys.
- Test one source fails — `partial=True`, `sources_failed` populated, other data present.
- Test all sources fail — returns empty data with all three in `sources_failed`.

### Adjudication
- Same pattern as coarse_filter/methods_analysis tests:
  - Paper assessed and updated (risk_tier, stage3_result, recommended_action, pipeline_stage).
  - Partial enrichment flag propagated correctly.
  - LLM error leaves paper at METHODS_ANALYSED.
  - Tier threshold filtering (paper below threshold skipped).

### Orchestrator
- Integration test with all clients mocked: verify stages run in order, stats populated correctly.
- Test stage failure isolation: one stage errors, others still process eligible papers.
- Test empty pipeline (no new papers): completes without error.
- Test date range calculation.
- Test PipelineRun row created and updated with stats.

### Scheduler
- Test scheduler starts and schedules a job at the configured hour.
- Test `trigger_run()` executes immediately.
- Test `update_schedule()` changes the cron time.
- Test `pause()` / `resume()` toggle.
- Test `get_status()` returns correct state.

## File Structure

```
pipeline/
├── enrichment/
│   ├── __init__.py
│   ├── openalex.py          # OpenAlex API client
│   ├── semantic_scholar.py  # Semantic Scholar API client
│   ├── orcid.py             # ORCID public API client
│   └── enricher.py          # Orchestrates all three sources
├── triage/
│   ├── prompts.py           # Modified: add adjudication prompt + tool schema
│   └── adjudication.py      # Stage 5: Opus contextual review
├── models.py                # Modified: add enrichment_data + PipelineRun
├── config.py                # Modified: add enrichment/adjudication settings
├── orchestrator.py          # Daily pipeline orchestrator (pure async)
├── scheduler.py             # APScheduler wrapper (long-lived process)
└── __main__.py              # Entry point: one-shot or --schedule mode

tests/
├── test_openalex.py
├── test_semantic_scholar.py
├── test_orcid.py
├── test_enricher.py
├── test_adjudication.py
├── test_orchestrator.py
└── test_scheduler.py
```
