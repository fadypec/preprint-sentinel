# DURC Preprint Triage — Developer Guide

Guide for setting up a local development environment, running the pipeline, and contributing code.

---

## Prerequisites

- **Python 3.11+** (the pipeline uses async/await, match statements, and modern type hints)
- **Node.js 22+** (for the Next.js dashboard)
- **PostgreSQL 16+** (or a managed Postgres instance like Supabase)
- **Git** with pre-commit hooks configured

---

## Initial Setup

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/fadypec/preprint-sentinel.git
cd preprint-sentinel

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Set up pre-commit hooks (ruff lint + format)
pre-commit install
```

### 2. Set up the database

```bash
# Create the database
createdb durc_triage

# Run migrations
alembic upgrade head
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys:
#   ANTHROPIC_API_KEY — required for LLM triage
#   DATABASE_URL — your PostgreSQL connection string
#   NCBI_API_KEY — optional, increases PubMed rate limit
```

See `docs/OPERATIONS.md` for the full list of environment variables.

### 4. Install dashboard dependencies

```bash
cd dashboard
npm install --legacy-peer-deps
npx prisma generate
cd ..
```

---

## Running Locally

### Pipeline (Python)

```bash
# Run a single pipeline execution (last 2 days)
python -m pipeline

# Run with custom date range
python -m pipeline --from-date 2026-04-01 --to-date 2026-04-10

# Run with full PubMed (not MeSH-filtered)
python -m pipeline --pubmed-query-mode all

# Skip backlog processing
python -m pipeline --skip-backlog
```

### Dashboard (Next.js)

```bash
cd dashboard
npm run dev
# Open http://localhost:3000
```

### Both together (typical development)

Terminal 1: `cd dashboard && npm run dev`
Terminal 2: `python -m pipeline` (when you want to trigger a run)

---

## Running Tests

### Python tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=pipeline --cov-report=term-missing

# Single test file
pytest tests/test_ingest.py -v

# Single test
pytest tests/test_dedup.py::TestDoiMatch::test_doi_exact_match -v
```

### Dashboard tests

```bash
cd dashboard
npm test           # Single run
npm run test:watch # Watch mode
```

### Linting

```bash
# Python
ruff check pipeline/ tests/
ruff format --check pipeline/ tests/
mypy pipeline/

# Dashboard
cd dashboard
npm run lint
npx tsc --noEmit
```

---

## Project Structure

```
├── pipeline/                 # Python backend pipeline
│   ├── __main__.py           # CLI entry point
│   ├── config.py             # Settings from .env (pydantic)
│   ├── models.py             # SQLAlchemy ORM models
│   ├── db.py                 # Database connection
│   ├── orchestrator.py       # Main pipeline orchestration
│   ├── scheduler.py          # APScheduler cron
│   ├── alerts.py             # Slack/email failure alerts
│   ├── http_retry.py         # Shared retry utility
│   ├── ingest/               # Data source clients
│   │   ├── biorxiv.py        # bioRxiv + medRxiv
│   │   ├── pubmed.py         # PubMed E-utilities
│   │   ├── europepmc.py      # Europe PMC
│   │   ├── arxiv.py          # arXiv
│   │   ├── crossref.py       # Crossref (Research Square, ChemRxiv, SSRN)
│   │   ├── zenodo.py         # Zenodo
│   │   └── dedup.py          # 3-tier deduplication
│   ├── fulltext/             # Full-text retrieval + parsing
│   ├── triage/               # LLM classification stages
│   │   ├── prompts.py        # All prompt templates
│   │   ├── coarse_filter.py  # Stage 2: Haiku screening
│   │   ├── methods_analysis.py  # Stage 4: Sonnet assessment
│   │   └── adjudication.py   # Stage 5: Opus review
│   └── enrichment/           # Author/institution context
│       ├── openalex.py
│       ├── semantic_scholar.py
│       ├── orcid.py
│       └── crossref.py       # Funder info
│
├── dashboard/                # Next.js frontend
│   ├── app/                  # Pages and API routes
│   ├── components/           # React components
│   └── lib/                  # Utilities and queries
│
├── tests/                    # Python test suite
├── scripts/                  # Operational scripts
├── alembic/                  # Database migrations
└── docs/                     # Documentation
    ├── API.md                # API reference
    ├── OPERATIONS.md         # Operations runbook
    └── DEVELOPMENT.md        # This file
```

---

## Adding a New Ingest Source

All ingest clients follow the same pattern. To add a new source:

1. **Create the client** at `pipeline/ingest/new_source.py`:

```python
class NewSourceClient:
    def __init__(self, request_delay=1.0, max_retries=3):
        self._client = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def fetch_papers(self, from_date, to_date):
        # Paginate through API, yield normalised dicts
        yield {
            "doi": "...",
            "title": "...",
            "authors": [{"name": "..."}],
            "source_server": SourceServer.NEW_SOURCE,
            "posted_date": date(...),
            # ... all fields from the common schema
        }
```

2. **Add the SourceServer enum value** in `pipeline/models.py` (if not already present)

3. **Add config settings** in `pipeline/config.py`:

```python
new_source_request_delay: float = 1.0
```

4. **Register in the orchestrator** — add to the `sources` list in `orchestrator.py:_run_ingest()`

5. **Write tests** in `tests/test_new_source.py` following the `TestNormalise`, `TestFetch`, `TestRetry` pattern

6. **Update the dashboard** — add the source to the filter dropdown in `dashboard/components/paper-filters.tsx`

---

## Debugging Tips

### Inspecting a paper in the database

```bash
# Find a specific paper
python -c "
import asyncio
from pipeline.db import make_engine, make_session_factory
from pipeline.config import get_settings
from sqlalchemy import text

async def query():
    s = get_settings()
    engine = make_engine(s.database_url.get_secret_value())
    sf = make_session_factory(engine)
    async with sf() as session:
        r = await session.execute(text(
            \"SELECT id, title, risk_tier, aggregate_score, pipeline_stage \"
            \"FROM papers WHERE title LIKE '%keyword%' LIMIT 5\"
        ))
        for row in r.mappings().all():
            print(dict(row))
    await engine.dispose()

asyncio.run(query())
"
```

### Viewing pipeline logs

```bash
# Latest log
ls -lt logs/pipeline-*.log | head -1

# Follow a running pipeline
tail -f logs/pipeline-*.log
```

### Reprocessing failed papers

```bash
# Via dashboard: Pipeline page → "Fix Errors" → "Run Pipeline" with backlog
# Via CLI:
python -m scripts.resume_pipeline
```

### Checking enrichment data for a paper

Use the dashboard paper detail page, or query the `enrichment_data` JSONB column directly:

```sql
SELECT enrichment_data->'openalex'->>'primary_institution',
       enrichment_data->'crossref'->'funders'
FROM papers WHERE id = 'paper-uuid-here';
```

---

## Code Conventions

- **Python:** ruff for linting/formatting (line length 100), mypy for type checking
- **TypeScript:** ESLint with Next.js config, strict mode enabled
- **Commits:** conventional commit format (`feat:`, `fix:`, `chore:`, `docs:`)
- **Tests:** pytest with async support; Vitest for frontend
- **Branches:** feature work on branches, merge to main via fast-forward
