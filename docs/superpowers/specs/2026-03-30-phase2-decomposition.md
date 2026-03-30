# Phase 2: Complete Backend Pipeline — Decomposition

> **Context:** Phase 1 built models, bioRxiv/medRxiv ingest, dedup, and Alembic migrations. Phase 2 completes the entire backend pipeline end-to-end, broken into three sub-projects built in order.

## Sub-project 1: Additional Ingest Clients (Europe PMC + PubMed)

**Goal:** Add two more Tier 1 data sources following the established bioRxiv client pattern.

**Components:**
- `pipeline/ingest/europepmc.py` — Europe PMC REST API client. Critical aggregator indexing 35+ preprint servers. Use `SRC:PPR` filter for preprints.
- `pipeline/ingest/pubmed.py` — PubMed E-utilities client (esearch + efetch). XML/JSON responses. Requires NCBI API key for 10 req/s rate limit.
- Integration with existing dedup engine (new papers go through the same three-tier cascade).
- New config fields for NCBI API key, Europe PMC settings.

**Dependencies:** Phase 1 complete (models, dedup, config).
**Independent of:** Triage stages, enrichment, orchestrator.

---

## Sub-project 2: Triage Pipeline (Stages 2-4)

**Goal:** Build the core AI classification chain from coarse filter through methods analysis.

**Components:**
- `pipeline/triage/coarse_filter.py` — Stage 2: Haiku-tier binary classification on title+abstract. ~95% filter rate.
- `pipeline/triage/prompts.py` — Centralised prompt templates with versioning.
- `pipeline/fulltext/retriever.py` — Stage 3: Retrieval cascade (bioRxiv XML → Europe PMC → PMC OA → Unpaywall → fallback).
- `pipeline/fulltext/jats_parser.py` — JATS XML methods section extraction.
- `pipeline/fulltext/html_parser.py` — HTML fallback extraction.
- `pipeline/fulltext/unpaywall.py` — Unpaywall API client for OA full-text URLs.
- `pipeline/triage/methods_analysis.py` — Stage 4: Sonnet-tier 6-dimension risk rubric assessment.
- AssessmentLog entries for every LLM call (audit trail).

**Dependencies:** Sub-project 1 not strictly required, but models and ingest infrastructure from Phase 1 are.
**Key integration:** Updates paper.pipeline_stage, paper.stage1_result/stage2_result, paper.risk_tier, paper.aggregate_score.

---

## Sub-project 3: Enrichment, Adjudication, Orchestration

**Goal:** Add contextual enrichment, expert-tier adjudication, and wire everything into a runnable daily pipeline.

**Components:**
- `pipeline/enrichment/openalex.py` — OpenAlex API client for author/institution/citation metadata.
- `pipeline/triage/adjudication.py` — Stage 5: Opus-tier contextual review using Stage 4 assessment + enrichment data + full text.
- `pipeline/orchestrator.py` — Main pipeline orchestration: ingest → dedup → coarse filter → full-text → methods analysis → adjudication.
- `pipeline/scheduler.py` — APScheduler or similar for daily cron (06:00 UTC).

**Dependencies:** Sub-projects 1 and 2 must be complete.
**Key integration:** Ties all stages together. Orchestrator manages the full paper lifecycle.

---

## Build Order

1. **Sub-project 1** (ingest clients) — can start immediately, follows established patterns
2. **Sub-project 2** (triage pipeline) — core intelligence, largest scope
3. **Sub-project 3** (enrichment + orchestration) — final integration, makes the pipeline runnable

Each sub-project gets its own design spec, implementation plan, and review cycle.
