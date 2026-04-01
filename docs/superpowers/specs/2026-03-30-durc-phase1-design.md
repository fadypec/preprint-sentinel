# Phase 1 Design: Core Pipeline — Ingest, Models, Dedup

**Date:** 2026-03-30
**Scope:** Project scaffold, database models, bioRxiv/medRxiv ingest client, deduplication engine, tests.
**Parent spec:** `CLAUDE.md` (full pipeline spec)

---

## 1. Project Scaffold & Configuration

### 1.1 `pyproject.toml`

- **Build system:** `hatchling` (PEP 517-compliant).
- **Dependency management:** `uv`.
- **Python:** `>=3.11`

**Core dependencies:**

| Package | Purpose |
|---------|---------|
| `anthropic` | LLM calls (Haiku/Sonnet/Opus) |
| `httpx` | Async HTTP client for all external API calls |
| `sqlalchemy[asyncio]` | Async ORM + query builder |
| `asyncpg` | PostgreSQL async driver (production) |
| `alembic` | Database migrations |
| `structlog` | Structured JSON logging |
| `pydantic-settings` | Typed configuration from env vars |
| `python-dotenv` | `.env` file loading |
| `rapidfuzz` | Fast fuzzy string matching for dedup |
| `lxml` | JATS XML parsing (Phase 1 prep; used in Phase 1 tests) |
| `apscheduler` | Task scheduling (used in later phases but declared now) |

**Dev dependencies:**

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `aiosqlite` | In-memory SQLite for fast unit tests |
| `respx` | Mock `httpx` transports (no monkeypatching) |
| `ruff` | Linter + formatter |

### 1.2 `pipeline/config.py`

Uses `pydantic-settings.BaseSettings` with a nested `model_config` pointing at `.env`.

```python
class Settings(BaseSettings):
    database_url: str
    anthropic_api_key: SecretStr          # SecretStr prevents accidental logging
    ncbi_api_key: str = ""
    unpaywall_email: str = ""
    openalex_email: str = ""
    semantic_scholar_api_key: SecretStr = SecretStr("")

    stage1_model: str = "claude-haiku-4-5-20251001"
    stage2_model: str = "claude-sonnet-4-6"
    stage3_model: str = "claude-opus-4-6"
    coarse_filter_threshold: float = 0.8
    daily_run_hour: int = 6

    # Rate-limit config (seconds between requests per source)
    biorxiv_request_delay: float = 1.0
    pubmed_request_delay: float = 0.1     # 10 req/s with API key

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir=None,
    )
```

**Cybersecurity notes:**
- All API keys and secrets use `pydantic.SecretStr`. The `__repr__` and `__str__` methods redact the value, so keys never appear in logs, tracebacks, or `structlog` output.
- `Settings` is instantiated once and imported — no repeated `os.getenv()` calls scattered across modules.

### 1.3 `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: durc
      POSTGRES_PASSWORD: durc_local       # local-only; never used in production
      POSTGRES_DB: durc_triage
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U durc"]
      interval: 5s
      retries: 3

volumes:
  pgdata:
```

**Cybersecurity notes:**
- The Postgres container binds to `localhost` only (Docker default for bridge mode).
- Credentials are local-dev-only and explicitly labelled as such. A `.env.example` documents the production pattern (managed secrets via env vars or a vault).

### 1.4 `.env.example`

```bash
# === Database ===
DATABASE_URL=postgresql+asyncpg://durc:durc_local@localhost:5432/durc_triage

# === Anthropic ===
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME

# === External APIs (all free) ===
NCBI_API_KEY=
UNPAYWALL_EMAIL=
OPENALEX_EMAIL=

# === Pipeline tuning ===
DAILY_RUN_HOUR=6
COARSE_FILTER_THRESHOLD=0.8
```

### 1.5 Logging (`pipeline/logging.py`)

Initialise `structlog` once at import time with:

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
```

**Information accessibility notes:**
- Every log line is structured JSON — machine-parseable, greppable, and ready for ingestion into any log aggregator.
- `merge_contextvars` allows per-request context (e.g., `source=biorxiv`, `cursor=120`) to propagate through deeply nested calls without threading log context manually.
- Sensitive fields are never logged because `SecretStr` values render as `"**********"`.

---

## 2. Database Models

### 2.1 Design principles

- **Append-only audit trail:** Every LLM assessment is logged in `assessment_logs` with the full prompt and response. The `papers` table stores only the *latest* classification result. If a paper is re-screened (e.g., after a prompt update), the old assessment is preserved in the log and a new row is appended.
- **Indexed for the access patterns that matter:** DOI lookup, date-range scans, risk-tier filtering, full-text search on titles/abstracts.
- **Enums over free text** for controlled vocabularies (`pipeline_stage`, `risk_tier`, `source_server`, `recommended_action`). This prevents typo-driven bugs and makes queries predictable.
- **UUIDs as primary keys.** Papers arrive from multiple sources and may be cross-referenced — auto-increment IDs create coupling to insertion order. UUIDs are globally unique and safe for distributed or batch inserts.

### 2.2 `pipeline/models.py`

#### Enums

```python
class SourceServer(str, enum.Enum):
    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    EUROPEPMC = "europepmc"
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    RESEARCH_SQUARE = "research_square"
    CHEMRXIV = "chemrxiv"
    ZENODO = "zenodo"
    SSRN = "ssrn"

class PipelineStage(str, enum.Enum):
    INGESTED = "ingested"
    COARSE_FILTERED = "coarse_filtered"
    FULLTEXT_RETRIEVED = "fulltext_retrieved"
    METHODS_ANALYSED = "methods_analysed"
    ADJUDICATED = "adjudicated"

class RiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RecommendedAction(str, enum.Enum):
    ARCHIVE = "archive"
    MONITOR = "monitor"
    REVIEW = "review"
    ESCALATE = "escalate"

class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    UNDER_REVIEW = "under_review"
    CONFIRMED_CONCERN = "confirmed_concern"
    FALSE_POSITIVE = "false_positive"
    ARCHIVED = "archived"

class DedupRelationship(str, enum.Enum):
    DUPLICATE = "duplicate"
    PUBLISHED_VERSION = "published_version"
    UPDATED_VERSION = "updated_version"
    CROSS_POSTED = "cross_posted"
```

#### `Paper` model

```python
class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID]          = mapped_column(primary_key=True, default=uuid.uuid4)
    doi: Mapped[str | None]        = mapped_column(String(255), index=True, unique=False)
    title: Mapped[str]             = mapped_column(Text, nullable=False)
    authors: Mapped[list[dict]]    = mapped_column(JSONB, nullable=False, default=list)
    corresponding_author: Mapped[str | None]      = mapped_column(String(512))
    corresponding_institution: Mapped[str | None]  = mapped_column(String(512))
    abstract: Mapped[str | None]   = mapped_column(Text)
    source_server: Mapped[SourceServer] = mapped_column(
        SQLEnum(SourceServer, name="source_server", create_constraint=True)
    )
    posted_date: Mapped[date]      = mapped_column(Date, index=True)
    subject_category: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int]           = mapped_column(Integer, default=1)

    # Full text
    full_text_url: Mapped[str | None]     = mapped_column(Text)
    full_text_retrieved: Mapped[bool]     = mapped_column(Boolean, default=False)
    full_text_content: Mapped[str | None] = mapped_column(Text)
    methods_section: Mapped[str | None]   = mapped_column(Text)

    # Pipeline state
    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        SQLEnum(PipelineStage, name="pipeline_stage", create_constraint=True),
        default=PipelineStage.INGESTED, index=True,
    )

    # Classification results (latest only; history in assessment_logs)
    stage1_result: Mapped[dict | None]  = mapped_column(JSONB)
    stage2_result: Mapped[dict | None]  = mapped_column(JSONB)
    stage3_result: Mapped[dict | None]  = mapped_column(JSONB)
    risk_tier: Mapped[RiskTier | None]  = mapped_column(
        SQLEnum(RiskTier, name="risk_tier", create_constraint=True), index=True,
    )
    recommended_action: Mapped[RecommendedAction | None] = mapped_column(
        SQLEnum(RecommendedAction, name="recommended_action", create_constraint=True),
    )
    aggregate_score: Mapped[int | None] = mapped_column(Integer)

    # Analyst workflow
    review_status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus, name="review_status", create_constraint=True),
        default=ReviewStatus.UNREVIEWED, index=True,
    )
    analyst_notes: Mapped[str | None] = mapped_column(Text)

    # Dedup
    is_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("papers.id"), index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
```

**Indexes (declared in `__table_args__`):**

| Index | Columns | Purpose |
|-------|---------|---------|
| `ix_papers_doi` | `doi` | Fast dedup lookup |
| `ix_papers_posted_date` | `posted_date` | Date-range queries for daily feed |
| `ix_papers_pipeline_stage` | `pipeline_stage` | Identify papers awaiting next stage |
| `ix_papers_risk_tier` | `risk_tier` | Dashboard filtering |
| `ix_papers_review_status` | `review_status` | Analyst queue |
| `ix_papers_title_trgm` | `title` (GIN trigram) | Fuzzy title search for dedup and dashboard search |
| `ix_papers_tsv` | `tsvector(title \|\| abstract)` (GIN) | Full-text search on the dashboard |

**Cybersecurity notes:**
- `authors` is stored as `JSONB`, not as a raw string. SQLAlchemy parameterises all queries — no SQL injection vectors.
- `full_text_content` may contain HTML/XML from external sources. It is stored *as retrieved* (preserving provenance) but must be sanitised before rendering in the dashboard (output encoding, not input sanitisation — the pipeline stores raw data; the dashboard escapes it).
- The `doi` field is `unique=False` because in rare cases two different source records may share a DOI before dedup runs. The dedup engine resolves this; the DB does not enforce a constraint that would reject valid ingestion.

**Information accessibility notes:**
- The `tsvector` GIN index enables sub-millisecond full-text search across titles and abstracts directly in Postgres — no need for an external search engine at the initial volume.
- `JSONB` columns (`authors`, `stage1_result`, etc.) are queryable via Postgres JSON operators, so analysts can write ad-hoc queries like `WHERE stage2_result->>'risk_tier' = 'high'`.

#### `PaperGroup` model

```python
class PaperGroup(Base):
    __tablename__ = "paper_groups"

    id: Mapped[uuid.UUID]           = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    member_id: Mapped[uuid.UUID]    = mapped_column(ForeignKey("papers.id"), index=True)
    relationship: Mapped[DedupRelationship] = mapped_column(
        SQLEnum(DedupRelationship, name="dedup_relationship", create_constraint=True),
    )
    confidence: Mapped[float]       = mapped_column(Float, default=1.0)
    strategy_used: Mapped[str]      = mapped_column(String(50))
    created_at: Mapped[datetime]    = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("canonical_id", "member_id", name="uq_paper_group_pair"),
    )
```

#### `AssessmentLog` model

```python
class AssessmentLog(Base):
    __tablename__ = "assessment_logs"

    id: Mapped[uuid.UUID]          = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID]    = mapped_column(ForeignKey("papers.id"), index=True)
    stage: Mapped[str]             = mapped_column(String(50), index=True)
    model_used: Mapped[str]        = mapped_column(String(100))
    prompt_version: Mapped[str]    = mapped_column(String(50))
    prompt_text: Mapped[str]       = mapped_column(Text)
    raw_response: Mapped[str]      = mapped_column(Text)
    parsed_result: Mapped[dict | None] = mapped_column(JSONB)
    input_tokens: Mapped[int]      = mapped_column(Integer)
    output_tokens: Mapped[int]     = mapped_column(Integer)
    cost_estimate_usd: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None]      = mapped_column(Text)
    created_at: Mapped[datetime]   = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True,
    )
```

**Information accessibility notes:**
- The `assessment_logs` table is the single source of truth for *why* a paper was classified the way it was. Every LLM call is recorded with prompt, response, and parsed result. Analysts can trace any classification back to the exact model invocation.
- `prompt_version` enables prompt regression detection — when prompts change, you can query for papers assessed with older versions and optionally re-screen them.

### 2.3 `pipeline/db.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # detect stale connections before use
    pool_recycle=3600,         # recycle connections after 1 hour
    echo=False,                # set True only for debugging; never in production
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Code efficiency notes:**
- `pool_pre_ping=True` avoids the overhead of a failed query + retry when a connection has gone stale (common with managed Postgres that has idle timeouts).
- `expire_on_commit=False` prevents unnecessary re-fetches of attributes after commit — the objects remain usable without a round-trip.
- `pool_size=5` is deliberately conservative. The pipeline is single-process; 5 connections support concurrent ingest + dedup without exhausting a free-tier Postgres connection limit (typically 20-60).

### 2.4 Alembic setup

- `alembic init alembic` to scaffold the migrations directory.
- `alembic/env.py` is configured to use the async engine from `pipeline.db` and the `Base.metadata` from `pipeline.models`.
- The initial migration auto-generates from the model definitions.
- The `pg_trgm` extension and the trigram/tsvector GIN indexes are created in the migration (not in model `__table_args__`) because they require `CREATE EXTENSION` which is a superuser operation that should be explicit.

---

## 3. bioRxiv / medRxiv Ingest Client

### 3.1 `pipeline/ingest/biorxiv.py`

```python
class BiorxivClient:
    """Async client for the CSHL bioRxiv/medRxiv API.

    Usage:
        async with BiorxivClient(server="biorxiv") as client:
            async for paper in client.fetch_papers(from_date, to_date):
                ...
    """

    BASE_URL = "https://api.biorxiv.org/details"

    def __init__(
        self,
        server: Literal["biorxiv", "medrxiv"],
        request_delay: float = 1.0,
        max_retries: int = 3,
    ): ...

    async def __aenter__(self) -> "BiorxivClient": ...
    async def __aexit__(self, *exc) -> None: ...

    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        ...

    async def _fetch_page(self, from_date: date, to_date: date, cursor: int) -> dict:
        """Fetch a single page from the API with retry logic."""
        ...

    def _normalise(self, raw: dict) -> dict:
        """Map raw API fields to the common metadata schema."""
        ...
```

### 3.2 Pagination

The CSHL API returns 100 results per page. The response includes a `messages` array with a single object containing `total` (total matching papers) and `count` (papers in this page).

```
GET /details/biorxiv/2026-03-01/2026-03-30/0     → records 0-99
GET /details/biorxiv/2026-03-01/2026-03-30/100   → records 100-199
...until count_returned < 100 or cursor >= total
```

The client paginates by incrementing the cursor by 100 until:
- The API returns fewer than 100 results (last page), OR
- The cursor exceeds the `total` reported in the first response.

### 3.3 Rate limiting and retry

```python
async def _fetch_page(self, from_date: date, to_date: date, cursor: int) -> dict:
    url = f"{self.BASE_URL}/{self.server}/{from_date}/{to_date}/{cursor}"
    for attempt in range(1, self.max_retries + 1):
        await asyncio.sleep(self.request_delay)  # always wait before each request
        try:
            resp = await self._client.get(url, timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 503):
                backoff = min(2 ** attempt, 30)
                log.warning("rate_limited", status=resp.status_code, backoff=backoff)
                await asyncio.sleep(backoff)
                continue
            resp.raise_for_status()
        except httpx.TimeoutException:
            if attempt == self.max_retries:
                raise
            log.warning("timeout", attempt=attempt)
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Failed after {self.max_retries} retries: {url}")
```

**Code efficiency notes:**
- The `request_delay` is applied *before* each request (not after), so the final page doesn't incur an unnecessary trailing wait.
- The client yields papers via `AsyncGenerator` — it never accumulates all papers in memory. A 30-day fetch (~5,000 papers) uses O(100) memory at any time, not O(5,000).
- `timeout=30.0` prevents a hung connection from blocking the entire pipeline.

**Cybersecurity notes:**
- The URL is constructed from validated `date` objects and a `Literal["biorxiv", "medrxiv"]` parameter — no user-controlled strings are interpolated into the URL.
- `httpx` validates TLS certificates by default. All connections to `api.biorxiv.org` are HTTPS.
- Response bodies are not trusted: the `_normalise` method validates and coerces each field. Unexpected fields are silently dropped rather than passed through.

### 3.4 Normalisation

The `_normalise` method maps CSHL API fields to the common schema:

| CSHL API field | Common schema field | Notes |
|----------------|-------------------|-------|
| `biorxiv_doi` / `medrxiv_doi` | `doi` | Prefixed with `10.1101/` if not already |
| `title` | `title` | Stripped of trailing whitespace |
| `authors` | `authors` | Split on `; ` delimiter into `[{"name": ...}]` list |
| `author_corresponding` | `corresponding_author` | |
| `author_corresponding_institution` | `corresponding_institution` | |
| `abstract` | `abstract` | HTML entities decoded |
| `category` | `subject_category` | |
| `date` | `posted_date` | Parsed to `datetime.date` |
| `version` | `version` | Cast to `int` |
| `published` | *(stored as metadata)* | Tracks if preprint has a published version |

Fields not present in the API response (`full_text_url`, `full_text_content`, etc.) are set to their schema defaults.

**Information accessibility notes:**
- Every normalised paper includes a `source_server` tag (always `biorxiv` or `medrxiv`), so downstream stages and the dashboard can always trace a paper back to its origin.
- The raw API response is logged at `DEBUG` level for troubleshooting, while the normalised result is logged at `INFO` — structured logs support both operational monitoring and forensic debugging.

---

## 4. Deduplication Engine

### 4.1 `pipeline/ingest/dedup.py`

```python
@dataclass(frozen=True)
class DedupResult:
    is_duplicate: bool
    duplicate_of: uuid.UUID | None
    strategy_used: str              # "doi_match" | "title_author_similarity" | "title_author_date" | "none"
    confidence: float               # 1.0 for DOI match, 0.0-1.0 for fuzzy

class DedupEngine:
    def __init__(self, session: AsyncSession): ...

    async def check(self, paper: dict) -> DedupResult:
        """Run the three-tier dedup cascade. Returns on first match."""
        ...

    async def _check_doi(self, doi: str | None) -> DedupResult | None:
        """Tier 1: exact DOI match. O(1) via index."""
        ...

    async def _check_title_author(self, title: str, first_author_surname: str, posted_date: date) -> DedupResult | None:
        """Tier 2: fuzzy title (ratio > 0.92) + surname match within +-14 days."""
        ...

    async def _check_title_author_date(self, title: str, first_author_surname: str, posted_date: date) -> DedupResult | None:
        """Tier 3: for DOI-less papers. Title + author + date within +-7 days."""
        ...

    async def record_duplicate(self, canonical_id: uuid.UUID, member_id: uuid.UUID, result: DedupResult) -> None:
        """Create PaperGroup entry and set is_duplicate_of on the member paper."""
        ...
```

### 4.2 Three-tier matching

**Tier 1 — DOI exact match:**
```sql
SELECT id FROM papers WHERE doi = :doi AND id != :current_paper_id LIMIT 1;
```
- Indexed lookup. Returns immediately if found.
- Confidence: `1.0`.

**Tier 2 — Title + first author surname similarity:**
```sql
SELECT id, title, authors FROM papers
WHERE posted_date BETWEEN :date_minus_14 AND :date_plus_14
  AND id != :current_paper_id;
```
- The date window avoids a full-table scan — at ~5,000 papers/day, a 28-day window is ~140,000 rows, which is manageable.
- For each candidate, compute `rapidfuzz.fuzz.ratio(normalise(title_a), normalise(title_b))`.
- Title normalisation: lowercase, strip punctuation, collapse whitespace.
- If ratio > 0.92 AND first author surname matches (case-insensitive), it's a duplicate.
- Confidence: the `fuzz.ratio / 100`.

**Tier 3 — Title + author + date (DOI-less papers only):**
- Same as Tier 2 but with a tighter date window (±7 days) and a lower title similarity threshold (0.88) since DOI-less papers may have more title variation.
- Only invoked if the paper has no DOI.

### 4.3 Recording duplicates

When a duplicate is found:
1. The paper is still inserted into `papers` with `is_duplicate_of = canonical.id`.
2. A `PaperGroup` row is created: `(canonical_id, member_id, relationship, confidence, strategy_used)`.
3. The relationship type is inferred:
   - Same DOI → `DUPLICATE`
   - Same paper, different version → `UPDATED_VERSION`
   - Same paper, different server → `CROSS_POSTED`
4. All records are preserved for audit. The dashboard query filters `WHERE is_duplicate_of IS NULL` by default but allows analysts to view duplicates.

**Code efficiency notes:**
- Tier 2's date-windowed query is the most expensive operation. Using the `ix_papers_posted_date` index + the PostgreSQL trigram index (`ix_papers_title_trgm`) would allow the DB to do the fuzzy match. However, at Phase 1 volumes (<200K papers), pulling candidates into Python and using `rapidfuzz` (C-optimised) is faster and simpler than a database trigram query. This can be revisited if volume grows.
- The `DedupResult` is a frozen dataclass — immutable, hashable, and cheap to create.

**Cybersecurity notes:**
- All database queries use SQLAlchemy's parameterised query builder — no string interpolation into SQL.
- The dedup engine never trusts external data for control flow decisions. A crafted title that happens to match an existing paper will correctly be flagged as a duplicate (which is the desired behaviour) and stored alongside the original for audit.

---

## 5. Tests & Fixtures

### 5.1 `tests/conftest.py`

Shared pytest fixtures:

- **`db_session`**: Creates an in-memory `sqlite+aiosqlite:///:memory:` engine, runs `Base.metadata.create_all`, yields an `AsyncSession`, and tears down. Every test gets a clean database.
- **`biorxiv_fixture`**: Loads `tests/fixtures/sample_biorxiv.json` and returns the raw API response dict.

### 5.2 `tests/test_ingest.py`

| Test | What it verifies |
|------|-----------------|
| `test_fetch_single_page` | Mocks a single-page response (< 100 results). Verifies correct URL construction, that results are normalised, and that no pagination occurs. |
| `test_fetch_multiple_pages` | Mocks a 250-result response (3 pages). Verifies cursor increments by 100 and all 250 papers are yielded. |
| `test_rate_limit_retry` | Mocks a 429 on first attempt, 200 on second. Verifies exponential backoff was applied and the paper is returned. |
| `test_timeout_retry` | Mocks a `httpx.TimeoutException` on first attempt. Verifies retry and eventual success. |
| `test_normalise_fields` | Passes a raw API record through `_normalise`. Verifies all fields are correctly mapped: DOI format, author list parsing, date parsing, HTML entity decoding in abstracts. |
| `test_medrxiv_server` | Verifies that `BiorxivClient(server="medrxiv")` hits the `/medrxiv/` endpoint. |

All HTTP calls are mocked using `respx` (an `httpx`-native mock library — no monkeypatching of `aiohttp` or `requests`).

### 5.3 `tests/test_dedup.py`

| Test | Scenario | Expected |
|------|----------|----------|
| `test_doi_exact_match` | Insert paper A (DOI X), then check paper B (DOI X). | `DedupResult(is_duplicate=True, strategy="doi_match", confidence=1.0)` |
| `test_title_author_similarity` | Insert paper A ("Novel CRISPR approach to gene editing", Smith). Check paper B ("A novel CRISPR approach to gene editing", Smith). | `is_duplicate=True, strategy="title_author_similarity"` |
| `test_no_match` | Insert paper A. Check paper B with different DOI, title, and author. | `is_duplicate=False` |
| `test_doi_less_fallback` | Insert paper A (no DOI, title X, Smith, 2026-03-01). Check paper B (no DOI, title X~, Smith, 2026-03-03). | `is_duplicate=True, strategy="title_author_date"` |
| `test_title_below_threshold` | Insert paper A. Check paper B with similar but not matching title (ratio < 0.88). | `is_duplicate=False` |
| `test_date_window_respected` | Insert paper A (2026-01-01). Check paper B with matching title/author but date 2026-06-01. | `is_duplicate=False` (outside ±14 day window) |
| `test_duplicate_recorded_in_paper_group` | After a duplicate is found, verify a `PaperGroup` row exists with correct `canonical_id`, `member_id`, and `relationship`. |

Uses `aiosqlite` in-memory database. The trigram and tsvector indexes (Postgres-specific) are skipped in SQLite — the tests exercise the Python-side fuzzy matching logic which is the same regardless of database backend.

### 5.4 `tests/fixtures/sample_biorxiv.json`

A list of 10 paper records in the exact format returned by the CSHL API. Includes:
- 5 standard biology papers (ecology, structural biology, etc.)
- 2 virology papers (one gain-of-function adjacent)
- 1 synthetic biology paper
- 1 protein design paper
- 1 bioinformatics methods paper
- At least 2 papers with matching DOIs (to test dedup)
- At least 1 paper pair with similar but not identical titles (to test fuzzy dedup)

---

## 6. Cross-Cutting Concerns

### 6.1 Cybersecurity checklist

| Concern | Mitigation |
|---------|-----------|
| **SQL injection** | All queries via SQLAlchemy ORM/Core with parameterised binds. No raw SQL string interpolation. |
| **Secret leakage in logs** | All API keys use `pydantic.SecretStr`. `structlog` will render them as `"**********"`. |
| **Secret leakage in tracebacks** | `SecretStr.__repr__` is redacted. Python tracebacks showing `Settings` objects will not leak keys. |
| **Untrusted external data** | All API responses are validated and coerced by `_normalise`. Unexpected fields are dropped. Type mismatches raise logged warnings, not crashes. |
| **XXE attacks via XML** | When `lxml` is used in later phases for JATS parsing, it will be configured with `resolve_entities=False` and `no_network=True` to prevent XML External Entity attacks. Noted here for Phase 1 design; implemented when XML parsing is added. |
| **Dependency supply chain** | `uv.lock` pins exact dependency versions. `ruff` is the only dev tool with broad file access. No `eval()` or `exec()` anywhere. |
| **Database credentials** | Local-only credentials in `docker-compose.yml`. Production uses env vars (or vault). `.env` is in `.gitignore`. |
| **TLS enforcement** | `httpx` verifies TLS certificates by default. No `verify=False` anywhere. |

### 6.2 Code efficiency checklist

| Concern | Approach |
|---------|---------|
| **Memory** | Ingest client yields papers via `AsyncGenerator` — O(page_size) memory, not O(total). |
| **Database connections** | Connection pool (size 5, overflow 10) with pre-ping and 1-hour recycle. |
| **Dedup query cost** | Date-windowed queries prevent full-table scans. DOI lookup is indexed. |
| **API cost** | Not yet relevant (no LLM calls in Phase 1), but the `assessment_logs` table tracks token usage and cost for future monitoring. |
| **Unnecessary work** | Dedup cascade short-circuits on first match — if DOI matches, title similarity is never computed. |

### 6.3 Information accessibility checklist

| Concern | Approach |
|---------|---------|
| **Structured logging** | All logs are JSON. Every log entry includes source, operation, and context. |
| **Audit trail** | `assessment_logs` preserves full LLM prompt + response history. |
| **Full-text search** | PostgreSQL `tsvector` GIN index on `title || abstract` for dashboard queries. |
| **Queryable JSON** | `JSONB` columns for authors, stage results — queryable with Postgres JSON operators. |
| **Dedup provenance** | `PaperGroup` records which strategy matched and at what confidence, so analysts can audit dedup decisions. |
| **Pipeline observability** | `pipeline_stage` column + `updated_at` timestamps let you query for stuck papers (e.g., `WHERE pipeline_stage = 'ingested' AND updated_at < now() - interval '2 days'`). |
