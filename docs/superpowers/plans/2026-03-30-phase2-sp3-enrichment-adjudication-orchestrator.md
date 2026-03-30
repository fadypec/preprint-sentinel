# Phase 2 SP3: Enrichment, Adjudication & Orchestrator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the pipeline backend with enrichment from OpenAlex/Semantic Scholar/ORCID, Opus adjudication with configurable thresholds, APScheduler-based scheduling, and a daily pipeline orchestrator.

**Architecture:** Three enrichment clients feed data into a merged enrichment_data column on Paper. Papers above the adjudication threshold go to Opus for contextual review. The orchestrator ties all pipeline stages together as a single async function, wrapped by APScheduler for daily execution.

**Tech Stack:** Python 3.11+, httpx (async HTTP), SQLAlchemy async ORM, Anthropic SDK, APScheduler 3.x, structlog, pytest/respx

---

### Task 1: Config and model updates

**Files:**
- Modify: `pipeline/config.py`
- Modify: `pipeline/models.py`
- Create: `pipeline/enrichment/__init__.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_settings_sp3_defaults(monkeypatch):
    """SP3 config fields have correct defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    from pipeline.config import Settings

    s = Settings()
    assert s.openalex_request_delay == 0.1
    assert s.semantic_scholar_request_delay == 1.0
    assert s.orcid_request_delay == 1.0
    assert s.adjudication_min_tier == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_settings_sp3_defaults -v`
Expected: FAIL -- `AttributeError: 'Settings' object has no attribute 'openalex_request_delay'`

- [ ] **Step 3: Add new config fields**

Add to `pipeline/config.py` after the `pubmed_mesh_query` field (inside the `Settings` class, before the closing of the class):

```python
    # Enrichment rate limits
    openalex_request_delay: float = 0.1
    semantic_scholar_request_delay: float = 1.0
    orcid_request_delay: float = 1.0

    # Adjudication
    adjudication_min_tier: str = "high"  # "low", "medium", "high", "critical"
```

- [ ] **Step 4: Add enrichment_data column and PipelineRun model**

In `pipeline/models.py`, add the `enrichment_data` column to the `Paper` class. Insert it immediately after the `methods_section` field:

```python
    enrichment_data: Mapped[dict | None] = mapped_column(PlatformJSON)
```

Add the `PipelineRun` model after the `AssessmentLog` class:

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
    trigger: Mapped[str] = mapped_column(String(50))
```

- [ ] **Step 5: Create enrichment package**

Create `pipeline/enrichment/__init__.py`:

```python
```

(Empty file -- just makes it a Python package.)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: All config tests PASS (including the new `test_settings_sp3_defaults`)

- [ ] **Step 7: Verify models create correctly**

Run: `uv run pytest tests/test_models.py -v`
Expected: All model tests PASS (the `db_engine` fixture calls `create_all` which exercises all models including the new `PipelineRun` and the new `enrichment_data` column)

- [ ] **Step 8: Lint**

Run: `uv run ruff check pipeline/config.py pipeline/models.py tests/test_config.py`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add pipeline/config.py pipeline/models.py pipeline/enrichment/__init__.py tests/test_config.py
git commit -m "feat: add SP3 config fields, enrichment_data column, PipelineRun model"
```

---

### Task 2: OpenAlex client

**Files:**
- Create: `pipeline/enrichment/openalex.py`
- Create: `tests/test_openalex.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openalex.py`:

```python
"""Tests for pipeline.enrichment.openalex -- OpenAlex API client."""

from __future__ import annotations

import httpx
import respx


def _work_response() -> dict:
    """Build a realistic OpenAlex works API response."""
    return {
        "results": [
            {
                "id": "https://openalex.org/W1234567890",
                "cited_by_count": 42,
                "topics": [
                    {
                        "display_name": "Virology",
                        "score": 0.95,
                    },
                    {
                        "display_name": "Microbiology",
                        "score": 0.80,
                    },
                ],
                "authorships": [
                    {
                        "author": {
                            "id": "https://openalex.org/A1111",
                            "display_name": "Jane Smith",
                            "orcid": "https://orcid.org/0000-0001-2345-6789",
                        },
                        "institutions": [
                            {
                                "display_name": "MIT",
                                "country_code": "US",
                                "type": "education",
                            }
                        ],
                        "author_position": "first",
                    },
                    {
                        "author": {
                            "id": "https://openalex.org/A2222",
                            "display_name": "Bob Jones",
                            "orcid": None,
                        },
                        "institutions": [
                            {
                                "display_name": "Harvard",
                                "country_code": "US",
                                "type": "education",
                            }
                        ],
                        "author_position": "last",
                    },
                ],
                "primary_location": {
                    "source": {
                        "display_name": "Nature",
                    }
                },
                "grants": [
                    {"funder_display_name": "NIH"},
                    {"funder_display_name": "DARPA"},
                ],
            }
        ]
    }


def _author_response(works_count: int = 150, cited_by_count: int = 3200) -> dict:
    """Build a mock OpenAlex author response."""
    return {
        "id": "https://openalex.org/A1111",
        "display_name": "Jane Smith",
        "works_count": works_count,
        "cited_by_count": cited_by_count,
    }


class TestOpenAlexLookup:
    """Tests for OpenAlexClient.lookup."""

    @respx.mock
    async def test_successful_lookup(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(200, json=_work_response())
        )
        respx.get("https://api.openalex.org/authors/A1111").mock(
            return_value=httpx.Response(200, json=_author_response())
        )
        respx.get("https://api.openalex.org/authors/A2222").mock(
            return_value=httpx.Response(200, json=_author_response(80, 1500))
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result["openalex_work_id"] == "W1234567890"
        assert result["cited_by_count"] == 42
        assert len(result["topics"]) == 2
        assert result["topics"][0]["name"] == "Virology"
        assert result["topics"][0]["score"] == 0.95
        assert len(result["authors"]) == 2
        assert result["authors"][0]["name"] == "Jane Smith"
        assert result["authors"][0]["openalex_id"] == "A1111"
        assert result["authors"][0]["orcid"] == "0000-0001-2345-6789"
        assert result["authors"][0]["institution"] == "MIT"
        assert result["authors"][0]["institution_country"] == "US"
        assert result["authors"][0]["institution_type"] == "education"
        assert result["authors"][0]["works_count"] == 150
        assert result["authors"][0]["cited_by_count"] == 3200
        assert result["primary_institution"] == "MIT"
        assert result["primary_institution_country"] == "US"
        assert result["funder_names"] == ["NIH", "DARPA"]

    @respx.mock
    async def test_not_found_returns_none(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/missing")

        assert result is None

    @respx.mock
    async def test_404_returns_none(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(404)
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/gone")

        assert result is None

    @respx.mock
    async def test_retry_on_429(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        route = respx.get("https://api.openalex.org/works").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_work_response()),
            ]
        )
        respx.get("https://api.openalex.org/authors/A1111").mock(
            return_value=httpx.Response(200, json=_author_response())
        )
        respx.get("https://api.openalex.org/authors/A2222").mock(
            return_value=httpx.Response(200, json=_author_response(80, 1500))
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/retry")

        assert result is not None
        assert route.call_count == 2

    @respx.mock
    async def test_retry_on_503(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        route = respx.get("https://api.openalex.org/works").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=_work_response()),
            ]
        )
        respx.get("https://api.openalex.org/authors/A1111").mock(
            return_value=httpx.Response(200, json=_author_response())
        )
        respx.get("https://api.openalex.org/authors/A2222").mock(
            return_value=httpx.Response(200, json=_author_response(80, 1500))
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/retry503")

        assert result is not None
        assert route.call_count == 2

    @respx.mock
    async def test_author_lookup_failure_still_returns_data(self):
        """If author detail lookup fails, author data still has basic info."""
        from pipeline.enrichment.openalex import OpenAlexClient

        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(200, json=_work_response())
        )
        respx.get("https://api.openalex.org/authors/A1111").mock(
            return_value=httpx.Response(500)
        )
        respx.get("https://api.openalex.org/authors/A2222").mock(
            return_value=httpx.Response(500)
        )

        async with OpenAlexClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result["authors"][0]["name"] == "Jane Smith"
        # works_count/cited_by_count are None when author lookup fails
        assert result["authors"][0]["works_count"] is None
        assert result["authors"][0]["cited_by_count"] is None

    @respx.mock
    async def test_mailto_param_sent(self):
        from pipeline.enrichment.openalex import OpenAlexClient

        route = respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        async with OpenAlexClient(email="user@example.com", request_delay=0) as client:
            await client.lookup("10.1234/test")

        assert route.called
        request = route.calls[0].request
        assert b"mailto=user%40example.com" in request.url.raw_path or "mailto" in str(request.url)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_openalex.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.enrichment.openalex'`

- [ ] **Step 3: Implement the OpenAlex client**

Create `pipeline/enrichment/openalex.py`:

```python
"""Async client for the OpenAlex API -- author/institution metadata.

Usage:
    async with OpenAlexClient(email="you@example.com") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result["primary_institution"])
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    """Async client for the OpenAlex API."""

    def __init__(
        self,
        email: str,
        request_delay: float = 0.1,
        max_retries: int = 3,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OpenAlexClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> dict | None:
        """Look up a paper by DOI and return enrichment data, or None."""
        assert self._client is not None, "Use OpenAlexClient as async context manager"

        work = await self._fetch_work(doi)
        if work is None:
            return None

        # Extract work-level fields
        openalex_work_id = self._extract_id(work.get("id", ""))
        cited_by_count = work.get("cited_by_count", 0)

        topics = [
            {"name": t.get("display_name", ""), "score": t.get("score", 0.0)}
            for t in work.get("topics", [])
        ]

        grants = work.get("grants", []) or []
        funder_names = [g.get("funder_display_name", "") for g in grants if g.get("funder_display_name")]

        # Extract author data
        authorships = work.get("authorships", [])
        authors = []
        primary_institution = None
        primary_institution_country = None

        for authorship in authorships:
            author_data = authorship.get("author", {})
            institutions = authorship.get("institutions", [])
            first_inst = institutions[0] if institutions else {}

            author_id = self._extract_id(author_data.get("id", ""))
            orcid_raw = author_data.get("orcid")
            orcid = self._extract_orcid(orcid_raw) if orcid_raw else None

            # Fetch detailed author stats
            works_count = None
            author_cited = None
            if author_id:
                author_detail = await self._fetch_author(author_id)
                if author_detail is not None:
                    works_count = author_detail.get("works_count")
                    author_cited = author_detail.get("cited_by_count")

            author_entry = {
                "name": author_data.get("display_name", ""),
                "openalex_id": author_id,
                "orcid": orcid,
                "institution": first_inst.get("display_name"),
                "institution_country": first_inst.get("country_code"),
                "institution_type": first_inst.get("type"),
                "works_count": works_count,
                "cited_by_count": author_cited,
            }
            authors.append(author_entry)

            # Primary institution = first author's institution
            if authorship.get("author_position") == "first" or primary_institution is None:
                if first_inst.get("display_name"):
                    primary_institution = first_inst.get("display_name")
                    primary_institution_country = first_inst.get("country_code")

        return {
            "openalex_work_id": openalex_work_id,
            "cited_by_count": cited_by_count,
            "topics": topics,
            "authors": authors,
            "primary_institution": primary_institution,
            "primary_institution_country": primary_institution_country,
            "funder_names": funder_names,
        }

    async def _fetch_work(self, doi: str) -> dict | None:
        """Fetch work data from OpenAlex by DOI."""
        url = f"{BASE_URL}/works"
        params = {"filter": f"doi:{doi}", "mailto": self.email}

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    return results[0] if results else None
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="openalex",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", source="openalex", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"OpenAlex failed after {self.max_retries} retries: {doi}")

    async def _fetch_author(self, author_id: str) -> dict | None:
        """Fetch author detail from OpenAlex. Returns None on any error."""
        url = f"{BASE_URL}/authors/{author_id}"
        params = {"mailto": self.email}
        try:
            await asyncio.sleep(self.request_delay)
            resp = await self._client.get(url, params=params, timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPError, Exception):
            log.debug("openalex_author_error", author_id=author_id)
        return None

    @staticmethod
    def _extract_id(openalex_url: str) -> str:
        """Extract the short ID from an OpenAlex URL like 'https://openalex.org/W123'."""
        if "/" in openalex_url:
            return openalex_url.rsplit("/", 1)[-1]
        return openalex_url

    @staticmethod
    def _extract_orcid(orcid_url: str) -> str:
        """Extract ORCID ID from URL like 'https://orcid.org/0000-0001-2345-6789'."""
        if "/" in orcid_url:
            return orcid_url.rsplit("/", 1)[-1]
        return orcid_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openalex.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/enrichment/openalex.py tests/test_openalex.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/enrichment/openalex.py tests/test_openalex.py
git commit -m "feat: add OpenAlex enrichment client with retry and author lookup"
```

---

### Task 3: Semantic Scholar client

**Files:**
- Create: `pipeline/enrichment/semantic_scholar.py`
- Create: `tests/test_semantic_scholar.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_semantic_scholar.py`:

```python
"""Tests for pipeline.enrichment.semantic_scholar -- Semantic Scholar API client."""

from __future__ import annotations

import httpx
import respx


def _paper_response() -> dict:
    """Build a realistic Semantic Scholar paper response."""
    return {
        "paperId": "abc123def456",
        "title": "Test Paper on H5N1",
        "tldr": {"text": "This paper describes gain-of-function research on H5N1."},
        "citationCount": 15,
        "influentialCitationCount": 3,
        "authors": [
            {"authorId": "12345", "name": "Jane Smith"},
            {"authorId": "67890", "name": "Bob Jones"},
        ],
    }


def _author_response(
    h_index: int = 25, citation_count: int = 4500, paper_count: int = 80
) -> dict:
    """Build a mock Semantic Scholar author response."""
    return {
        "authorId": "12345",
        "name": "Jane Smith",
        "hIndex": h_index,
        "citationCount": citation_count,
        "paperCount": paper_count,
    }


class TestSemanticScholarLookup:
    """Tests for SemanticScholarClient.lookup."""

    @respx.mock
    async def test_successful_lookup(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test").mock(
            return_value=httpx.Response(200, json=_paper_response())
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(200, json=_author_response())
        )

        async with SemanticScholarClient(request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result["s2_paper_id"] == "abc123def456"
        assert result["tldr"] == "This paper describes gain-of-function research on H5N1."
        assert result["citation_count"] == 15
        assert result["influential_citation_count"] == 3
        assert result["first_author_h_index"] == 25
        assert result["first_author_paper_count"] == 80
        assert result["first_author_citation_count"] == 4500

    @respx.mock
    async def test_not_found_returns_none(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/missing").mock(
            return_value=httpx.Response(404)
        )

        async with SemanticScholarClient(request_delay=0) as client:
            result = await client.lookup("10.1234/missing")

        assert result is None

    @respx.mock
    async def test_no_api_key_mode(self):
        """Client works without an API key (no x-api-key header sent)."""
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        route = respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test").mock(
            return_value=httpx.Response(200, json=_paper_response())
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(200, json=_author_response())
        )

        async with SemanticScholarClient(api_key="", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        request = route.calls[0].request
        assert "x-api-key" not in request.headers

    @respx.mock
    async def test_api_key_sent_when_provided(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        route = respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test").mock(
            return_value=httpx.Response(200, json=_paper_response())
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(200, json=_author_response())
        )

        async with SemanticScholarClient(api_key="my-s2-key", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        request = route.calls[0].request
        assert request.headers["x-api-key"] == "my-s2-key"

    @respx.mock
    async def test_retry_on_429(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        route = respx.get(
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/retry"
        ).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_paper_response()),
            ]
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(200, json=_author_response())
        )

        async with SemanticScholarClient(request_delay=0) as client:
            result = await client.lookup("10.1234/retry")

        assert result is not None
        assert route.call_count == 2

    @respx.mock
    async def test_no_tldr_returns_none_for_tldr(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        paper = _paper_response()
        paper["tldr"] = None
        respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test").mock(
            return_value=httpx.Response(200, json=paper)
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(200, json=_author_response())
        )

        async with SemanticScholarClient(request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result["tldr"] is None

    @respx.mock
    async def test_author_lookup_failure_returns_none_for_author_fields(self):
        from pipeline.enrichment.semantic_scholar import SemanticScholarClient

        respx.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test").mock(
            return_value=httpx.Response(200, json=_paper_response())
        )
        respx.get("https://api.semanticscholar.org/graph/v1/author/12345").mock(
            return_value=httpx.Response(500)
        )

        async with SemanticScholarClient(request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result["first_author_h_index"] is None
        assert result["first_author_paper_count"] is None
        assert result["first_author_citation_count"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_semantic_scholar.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.enrichment.semantic_scholar'`

- [ ] **Step 3: Implement the Semantic Scholar client**

Create `pipeline/enrichment/semantic_scholar.py`:

```python
"""Async client for the Semantic Scholar Academic Graph API.

Usage:
    async with SemanticScholarClient(api_key="...") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result["first_author_h_index"])
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarClient:
    """Async client for the Semantic Scholar API."""

    def __init__(
        self,
        api_key: str = "",
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SemanticScholarClient:
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        self._client = httpx.AsyncClient(headers=headers)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> dict | None:
        """Look up a paper by DOI and return enrichment data, or None."""
        assert self._client is not None, "Use SemanticScholarClient as async context manager"

        paper = await self._fetch_paper(doi)
        if paper is None:
            return None

        s2_paper_id = paper.get("paperId", "")
        tldr_obj = paper.get("tldr")
        tldr = tldr_obj.get("text") if tldr_obj else None
        citation_count = paper.get("citationCount", 0)
        influential_citation_count = paper.get("influentialCitationCount", 0)

        # Fetch first author details
        first_author_h_index = None
        first_author_paper_count = None
        first_author_citation_count = None

        authors = paper.get("authors", [])
        if authors:
            first_author_id = authors[0].get("authorId")
            if first_author_id:
                author_detail = await self._fetch_author(first_author_id)
                if author_detail is not None:
                    first_author_h_index = author_detail.get("hIndex")
                    first_author_paper_count = author_detail.get("paperCount")
                    first_author_citation_count = author_detail.get("citationCount")

        return {
            "s2_paper_id": s2_paper_id,
            "tldr": tldr,
            "citation_count": citation_count,
            "influential_citation_count": influential_citation_count,
            "first_author_h_index": first_author_h_index,
            "first_author_paper_count": first_author_paper_count,
            "first_author_citation_count": first_author_citation_count,
        }

    async def _fetch_paper(self, doi: str) -> dict | None:
        """Fetch paper data from Semantic Scholar by DOI."""
        url = f"{BASE_URL}/paper/DOI:{doi}"
        params = {
            "fields": "title,tldr,citationCount,influentialCitationCount,authors",
        }

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="semantic_scholar",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning(
                    "timeout", source="semantic_scholar", attempt=attempt, backoff=backoff
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Semantic Scholar failed after {self.max_retries} retries: {doi}")

    async def _fetch_author(self, author_id: str) -> dict | None:
        """Fetch author detail. Returns None on any error."""
        url = f"{BASE_URL}/author/{author_id}"
        params = {"fields": "name,hIndex,citationCount,paperCount"}
        try:
            await asyncio.sleep(self.request_delay)
            resp = await self._client.get(url, params=params, timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPError, Exception):
            log.debug("s2_author_error", author_id=author_id)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_semantic_scholar.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/enrichment/semantic_scholar.py tests/test_semantic_scholar.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/enrichment/semantic_scholar.py tests/test_semantic_scholar.py
git commit -m "feat: add Semantic Scholar enrichment client with author h-index lookup"
```

---

### Task 4: ORCID client

**Files:**
- Create: `pipeline/enrichment/orcid.py`
- Create: `tests/test_orcid.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orcid.py`:

```python
"""Tests for pipeline.enrichment.orcid -- ORCID public API client."""

from __future__ import annotations

import httpx
import respx


def _search_response(orcid_id: str = "0000-0001-2345-6789") -> dict:
    """Build a mock ORCID search response."""
    return {
        "num-found": 1,
        "result": [
            {
                "orcid-identifier": {
                    "path": orcid_id,
                }
            }
        ],
    }


def _record_response(
    orcid_id: str = "0000-0001-2345-6789",
) -> dict:
    """Build a mock ORCID record response."""
    return {
        "orcid-identifier": {"path": orcid_id},
        "activities-summary": {
            "employments": {
                "affiliation-group": [
                    {
                        "summaries": [
                            {
                                "employment-summary": {
                                    "organization": {
                                        "name": "MIT",
                                    },
                                    "start-date": {"year": {"value": "2020"}},
                                    "end-date": None,
                                }
                            }
                        ]
                    },
                    {
                        "summaries": [
                            {
                                "employment-summary": {
                                    "organization": {
                                        "name": "Stanford",
                                    },
                                    "start-date": {"year": {"value": "2015"}},
                                    "end-date": {"year": {"value": "2020"}},
                                }
                            }
                        ]
                    },
                ]
            },
            "educations": {
                "affiliation-group": [
                    {
                        "summaries": [
                            {
                                "education-summary": {
                                    "organization": {
                                        "name": "Harvard",
                                    },
                                    "role-title": "PhD",
                                    "end-date": {"year": {"value": "2015"}},
                                }
                            }
                        ]
                    }
                ]
            },
        },
    }


class TestOrcidLookup:
    """Tests for OrcidClient.lookup."""

    @respx.mock
    async def test_direct_orcid_lookup(self):
        """When known_orcid is provided, skip search and go to record."""
        from pipeline.enrichment.orcid import OrcidClient

        respx.get("https://pub.orcid.org/v3.0/0000-0001-2345-6789/record").mock(
            return_value=httpx.Response(200, json=_record_response())
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Jane Smith", known_orcid="0000-0001-2345-6789")

        assert result is not None
        assert result["orcid_id"] == "0000-0001-2345-6789"
        assert result["current_institution"] == "MIT"
        assert "MIT (2020-present)" in result["employment_history"]
        assert "Stanford (2015-2020)" in result["employment_history"]
        assert "PhD, Harvard (2015)" in result["education"]

    @respx.mock
    async def test_name_search_path(self):
        """When no known_orcid, search by name first."""
        from pipeline.enrichment.orcid import OrcidClient

        respx.get("https://pub.orcid.org/v3.0/search/").mock(
            return_value=httpx.Response(200, json=_search_response())
        )
        respx.get("https://pub.orcid.org/v3.0/0000-0001-2345-6789/record").mock(
            return_value=httpx.Response(200, json=_record_response())
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Jane Smith")

        assert result is not None
        assert result["orcid_id"] == "0000-0001-2345-6789"
        assert result["current_institution"] == "MIT"

    @respx.mock
    async def test_not_found_returns_none(self):
        from pipeline.enrichment.orcid import OrcidClient

        respx.get("https://pub.orcid.org/v3.0/search/").mock(
            return_value=httpx.Response(200, json={"num-found": 0, "result": []})
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Nobody Noname")

        assert result is None

    @respx.mock
    async def test_record_404_returns_none(self):
        from pipeline.enrichment.orcid import OrcidClient

        respx.get("https://pub.orcid.org/v3.0/0000-0000-0000-0000/record").mock(
            return_value=httpx.Response(404)
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Jane Smith", known_orcid="0000-0000-0000-0000")

        assert result is None

    @respx.mock
    async def test_retry_on_429(self):
        from pipeline.enrichment.orcid import OrcidClient

        route = respx.get("https://pub.orcid.org/v3.0/0000-0001-2345-6789/record").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_record_response()),
            ]
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Jane Smith", known_orcid="0000-0001-2345-6789")

        assert result is not None
        assert route.call_count == 2

    @respx.mock
    async def test_empty_employment_history(self):
        from pipeline.enrichment.orcid import OrcidClient

        record = _record_response()
        record["activities-summary"]["employments"]["affiliation-group"] = []
        record["activities-summary"]["educations"]["affiliation-group"] = []

        respx.get("https://pub.orcid.org/v3.0/0000-0001-2345-6789/record").mock(
            return_value=httpx.Response(200, json=record)
        )

        async with OrcidClient(request_delay=0) as client:
            result = await client.lookup("Jane Smith", known_orcid="0000-0001-2345-6789")

        assert result is not None
        assert result["current_institution"] is None
        assert result["employment_history"] == []
        assert result["education"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orcid.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.enrichment.orcid'`

- [ ] **Step 3: Implement the ORCID client**

Create `pipeline/enrichment/orcid.py`:

```python
"""Async client for the ORCID Public API -- author identity and affiliations.

Usage:
    async with OrcidClient() as client:
        result = await client.lookup("Jane Smith", known_orcid="0000-0001-2345-6789")
        if result:
            print(result["current_institution"])
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://pub.orcid.org/v3.0"


class OrcidClient:
    """Async client for the ORCID Public API."""

    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OrcidClient:
        self._client = httpx.AsyncClient(
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, name: str, known_orcid: str | None = None) -> dict | None:
        """Look up an author by name or ORCID and return identity data, or None."""
        assert self._client is not None, "Use OrcidClient as async context manager"

        orcid_id = known_orcid
        if orcid_id is None:
            orcid_id = await self._search_by_name(name)
            if orcid_id is None:
                return None

        record = await self._fetch_record(orcid_id)
        if record is None:
            return None

        return self._parse_record(orcid_id, record)

    async def _search_by_name(self, name: str) -> str | None:
        """Search ORCID by name. Returns the first matching ORCID ID, or None."""
        parts = name.strip().split()
        if len(parts) >= 2:
            # Assume "Given Family" format
            given = parts[0]
            family = parts[-1]
            query = f"given-names:{given} AND family-name:{family}"
        else:
            query = f"family-name:{name}"

        url = f"{BASE_URL}/search/"
        params = {"q": query, "rows": 1}

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("result", [])
                    if not results:
                        return None
                    orcid_ident = results[0].get("orcid-identifier", {})
                    return orcid_ident.get("path")
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="orcid",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", source="orcid", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"ORCID search failed after {self.max_retries} retries")

    async def _fetch_record(self, orcid_id: str) -> dict | None:
        """Fetch the full ORCID record. Returns None on 404."""
        url = f"{BASE_URL}/{orcid_id}/record"

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="orcid",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", source="orcid", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"ORCID record failed after {self.max_retries} retries: {orcid_id}")

    def _parse_record(self, orcid_id: str, record: dict) -> dict:
        """Extract structured data from an ORCID record."""
        activities = record.get("activities-summary", {})

        # Employment history
        employment_groups = (
            activities.get("employments", {}).get("affiliation-group", [])
        )
        employment_history = []
        current_institution = None

        for group in employment_groups:
            summaries = group.get("summaries", [])
            for summary_wrapper in summaries:
                emp = summary_wrapper.get("employment-summary", {})
                org_name = emp.get("organization", {}).get("name", "")
                start_year = self._extract_year(emp.get("start-date"))
                end_date = emp.get("end-date")
                if end_date is None:
                    end_str = "present"
                    if current_institution is None:
                        current_institution = org_name
                else:
                    end_str = self._extract_year(end_date) or "?"

                start_str = start_year or "?"
                entry = f"{org_name} ({start_str}-{end_str})"
                employment_history.append(entry)

        # Education
        education_groups = (
            activities.get("educations", {}).get("affiliation-group", [])
        )
        education = []
        for group in education_groups:
            summaries = group.get("summaries", [])
            for summary_wrapper in summaries:
                edu = summary_wrapper.get("education-summary", {})
                org_name = edu.get("organization", {}).get("name", "")
                role = edu.get("role-title", "")
                end_year = self._extract_year(edu.get("end-date"))
                if role and org_name:
                    entry = f"{role}, {org_name}"
                elif org_name:
                    entry = org_name
                else:
                    continue
                if end_year:
                    entry += f" ({end_year})"
                education.append(entry)

        return {
            "orcid_id": orcid_id,
            "current_institution": current_institution,
            "employment_history": employment_history,
            "education": education,
        }

    @staticmethod
    def _extract_year(date_obj: dict | None) -> str | None:
        """Extract year string from an ORCID date object."""
        if date_obj is None:
            return None
        year = date_obj.get("year", {})
        if isinstance(year, dict):
            return year.get("value")
        return str(year) if year else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orcid.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/enrichment/orcid.py tests/test_orcid.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/enrichment/orcid.py tests/test_orcid.py
git commit -m "feat: add ORCID enrichment client with name search and record lookup"
```

---

### Task 5: Enricher

**Files:**
- Create: `pipeline/enrichment/enricher.py`
- Create: `tests/test_enricher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enricher.py`:

```python
"""Tests for pipeline.enrichment.enricher -- orchestrates all enrichment sources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _openalex_data() -> dict:
    return {
        "openalex_work_id": "W123",
        "cited_by_count": 42,
        "topics": [{"name": "Virology", "score": 0.95}],
        "authors": [
            {
                "name": "Jane Smith",
                "openalex_id": "A111",
                "orcid": "0000-0001-2345-6789",
                "institution": "MIT",
                "institution_country": "US",
                "institution_type": "education",
                "works_count": 150,
                "cited_by_count": 3200,
            }
        ],
        "primary_institution": "MIT",
        "primary_institution_country": "US",
        "funder_names": ["NIH"],
    }


def _s2_data() -> dict:
    return {
        "s2_paper_id": "abc123",
        "tldr": "A paper about H5N1.",
        "citation_count": 15,
        "influential_citation_count": 3,
        "first_author_h_index": 25,
        "first_author_paper_count": 80,
        "first_author_citation_count": 4500,
    }


def _orcid_data() -> dict:
    return {
        "orcid_id": "0000-0001-2345-6789",
        "current_institution": "MIT",
        "employment_history": ["MIT (2020-present)"],
        "education": ["PhD, Harvard (2015)"],
    }


class TestEnrichPaper:
    """Tests for enrich_paper function."""

    async def test_all_sources_succeed(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            # OpenAlex mock
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            # Semantic Scholar mock
            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(return_value=_s2_data())
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            # ORCID mock
            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is False
        assert result.sources_succeeded == ["openalex", "semantic_scholar", "orcid"]
        assert result.sources_failed == []
        assert result.data["openalex"]["openalex_work_id"] == "W123"
        assert result.data["s2"]["s2_paper_id"] == "abc123"
        assert result.data["orcid"]["orcid_id"] == "0000-0001-2345-6789"

    async def test_one_source_fails(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            # OpenAlex succeeds
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            # Semantic Scholar fails
            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(side_effect=RuntimeError("API down"))
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            # ORCID succeeds
            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is True
        assert "openalex" in result.sources_succeeded
        assert "orcid" in result.sources_succeeded
        assert result.sources_failed == ["semantic_scholar"]
        assert "openalex" in result.data
        assert "s2" not in result.data
        assert "orcid" in result.data

    async def test_all_sources_fail(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            for mock_cls in [mock_oa_cls, mock_s2_cls, mock_orcid_cls]:
                mock_inst = AsyncMock()
                mock_inst.lookup = AsyncMock(side_effect=RuntimeError("fail"))
                mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
                mock_inst.__aexit__ = AsyncMock(return_value=None)
                mock_cls.return_value = mock_inst

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is True
        assert result.sources_succeeded == []
        assert set(result.sources_failed) == {"openalex", "semantic_scholar", "orcid"}
        assert result.data == {}

    async def test_orcid_uses_known_orcid_from_openalex(self, db_session: AsyncSession):
        """ORCID client receives known_orcid extracted from OpenAlex data."""
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(return_value=_s2_data())
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            result = await enrich_paper(paper, mock_settings)

        # Verify ORCID was called with the known_orcid from OpenAlex
        mock_orcid.lookup.assert_called_once_with(
            "Jane Smith", known_orcid="0000-0001-2345-6789"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enricher.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.enrichment.enricher'`

- [ ] **Step 3: Implement the enricher**

Create `pipeline/enrichment/enricher.py`:

```python
"""Enrichment orchestrator -- merges data from OpenAlex, Semantic Scholar, and ORCID.

Usage:
    result = await enrich_paper(paper, settings)
    paper.enrichment_data = {**result.data, "_meta": {...}}
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from pipeline.enrichment.openalex import OpenAlexClient
from pipeline.enrichment.orcid import OrcidClient
from pipeline.enrichment.semantic_scholar import SemanticScholarClient
from pipeline.models import Paper

log = structlog.get_logger()


@dataclass(frozen=True)
class EnrichmentResult:
    """Result of enriching a single paper from all sources."""

    data: dict
    sources_succeeded: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    partial: bool = False


async def enrich_paper(paper: Paper, settings) -> EnrichmentResult:
    """Fetch enrichment data from all configured sources.

    Each source is wrapped in try/except -- individual failures are recorded
    but do not prevent other sources from being queried.
    """
    doi = paper.doi or ""
    corresponding_author = paper.corresponding_author or ""

    merged_data: dict = {}
    sources_succeeded: list[str] = []
    sources_failed: list[str] = []

    # Known ORCID from OpenAlex (populated below if available)
    known_orcid: str | None = None

    # 1. OpenAlex
    try:
        async with OpenAlexClient(
            email=settings.openalex_email,
            request_delay=settings.openalex_request_delay,
        ) as oa_client:
            oa_data = await oa_client.lookup(doi)
        if oa_data is not None:
            merged_data["openalex"] = oa_data
            sources_succeeded.append("openalex")
            # Extract ORCID for first/corresponding author
            known_orcid = _extract_orcid_from_openalex(oa_data, corresponding_author)
        else:
            # DOI not found is not an error, but no data to merge
            sources_succeeded.append("openalex")
    except Exception:
        log.warning("enrichment_openalex_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("openalex")

    # 2. Semantic Scholar
    try:
        s2_api_key = settings.semantic_scholar_api_key.get_secret_value()
        async with SemanticScholarClient(
            api_key=s2_api_key,
            request_delay=settings.semantic_scholar_request_delay,
        ) as s2_client:
            s2_data = await s2_client.lookup(doi)
        if s2_data is not None:
            merged_data["s2"] = s2_data
        sources_succeeded.append("semantic_scholar")
    except Exception:
        log.warning("enrichment_s2_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("semantic_scholar")

    # 3. ORCID (for corresponding/first author only)
    try:
        author_name = corresponding_author
        if not author_name:
            # Fall back to first author
            authors = paper.authors or []
            if authors and isinstance(authors, list) and len(authors) > 0:
                author_name = authors[0].get("name", "")

        if author_name:
            async with OrcidClient(
                request_delay=settings.orcid_request_delay,
            ) as orcid_client:
                orcid_data = await orcid_client.lookup(author_name, known_orcid=known_orcid)
            if orcid_data is not None:
                merged_data["orcid"] = orcid_data
        sources_succeeded.append("orcid")
    except Exception:
        log.warning("enrichment_orcid_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("orcid")

    partial = len(sources_failed) > 0

    log.info(
        "enrichment_complete",
        paper_id=str(paper.id),
        succeeded=sources_succeeded,
        failed=sources_failed,
        partial=partial,
    )

    return EnrichmentResult(
        data=merged_data,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        partial=partial,
    )


def _extract_orcid_from_openalex(oa_data: dict, corresponding_author: str) -> str | None:
    """Try to find the ORCID for the corresponding (or first) author from OpenAlex data."""
    authors = oa_data.get("authors", [])
    if not authors:
        return None

    # Try to match corresponding author by name
    if corresponding_author:
        corresponding_lower = corresponding_author.lower()
        for author in authors:
            if author.get("name", "").lower() in corresponding_lower or corresponding_lower in author.get("name", "").lower():
                if author.get("orcid"):
                    return author["orcid"]

    # Fall back to first author's ORCID
    first_author = authors[0]
    return first_author.get("orcid")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enricher.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/enrichment/enricher.py tests/test_enricher.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/enrichment/enricher.py tests/test_enricher.py
git commit -m "feat: add enrichment orchestrator merging OpenAlex, S2, and ORCID data"
```

---

### Task 6: Adjudication prompts

**Files:**
- Modify: `pipeline/triage/prompts.py`
- Modify: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

Add the following to the end of `tests/test_prompts.py`:

```python
class TestAdjudicationPromptConstants:
    """Verify adjudication prompt constants exist and are well-formed."""

    def test_adjudication_version_exists(self):
        from pipeline.triage.prompts import ADJUDICATION_VERSION

        assert isinstance(ADJUDICATION_VERSION, str)
        assert ADJUDICATION_VERSION.startswith("v")

    def test_adjudication_system_prompt_exists(self):
        from pipeline.triage.prompts import ADJUDICATION_SYSTEM_PROMPT

        assert isinstance(ADJUDICATION_SYSTEM_PROMPT, str)
        assert len(ADJUDICATION_SYSTEM_PROMPT) > 100
        assert "dual-use" in ADJUDICATION_SYSTEM_PROMPT.lower()
        assert "institutional" in ADJUDICATION_SYSTEM_PROMPT.lower()
        assert "enrichment" in ADJUDICATION_SYSTEM_PROMPT.lower()


class TestAdjudicateToolSchema:
    """Verify adjudication tool schema is valid."""

    def test_adjudicate_paper_tool_structure(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        assert ADJUDICATE_PAPER_TOOL["name"] == "adjudicate_paper"
        schema = ADJUDICATE_PAPER_TOOL["input_schema"]
        assert "adjusted_risk_tier" in schema["properties"]
        assert "adjusted_action" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert "partial_enrichment" in schema["properties"]
        assert "missing_sources" in schema["properties"]
        assert "institutional_context" in schema["properties"]
        assert "durc_oversight_indicators" in schema["properties"]
        assert "adjustment_reasoning" in schema["properties"]
        assert "summary" in schema["properties"]

    def test_adjudicate_paper_tool_required_fields(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        schema = ADJUDICATE_PAPER_TOOL["input_schema"]
        required = set(schema["required"])
        expected = {
            "adjusted_risk_tier",
            "adjusted_action",
            "confidence",
            "partial_enrichment",
            "missing_sources",
            "institutional_context",
            "durc_oversight_indicators",
            "adjustment_reasoning",
            "summary",
        }
        assert required == expected

    def test_adjusted_risk_tier_enum(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        tier = ADJUDICATE_PAPER_TOOL["input_schema"]["properties"]["adjusted_risk_tier"]
        assert tier["enum"] == ["low", "medium", "high", "critical"]

    def test_adjusted_action_enum(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        action = ADJUDICATE_PAPER_TOOL["input_schema"]["properties"]["adjusted_action"]
        assert action["enum"] == ["archive", "monitor", "review", "escalate"]


class TestAdjudicationMessageFormatting:
    """Verify adjudication message formatting."""

    def test_format_with_all_data(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="H5N1 GoF Paper",
            abstract="We enhanced transmissibility.",
            methods="Serial passage in ferrets.",
            stage2_result={"risk_tier": "high", "aggregate_score": 10},
            enrichment_data={"openalex": {"primary_institution": "MIT"}},
            sources_failed=[],
        )
        assert "H5N1 GoF Paper" in msg
        assert "We enhanced transmissibility." in msg
        assert "Serial passage in ferrets." in msg
        assert "high" in msg
        assert "MIT" in msg

    def test_format_without_methods(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="Title",
            abstract="Abstract",
            methods=None,
            stage2_result={"risk_tier": "high"},
            enrichment_data={},
            sources_failed=["semantic_scholar"],
        )
        assert "Title" in msg
        assert "Abstract" in msg
        assert "methods" in msg.lower() or "not available" in msg.lower()
        assert "semantic_scholar" in msg

    def test_format_with_enrichment_failures(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="Title",
            abstract="Abstract",
            methods=None,
            stage2_result={},
            enrichment_data={},
            sources_failed=["openalex", "orcid"],
        )
        assert "openalex" in msg
        assert "orcid" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompts.py::TestAdjudicationPromptConstants -v`
Expected: FAIL -- `ImportError: cannot import name 'ADJUDICATION_VERSION' from 'pipeline.triage.prompts'`

- [ ] **Step 3: Add adjudication prompts and tool schema to prompts.py**

Add the following to `pipeline/triage/prompts.py`. The additions go at the end of the existing file, following the same section patterns.

After the existing `METHODS_ANALYSIS_VERSION` in the Versions section, add:

```python
ADJUDICATION_VERSION = "v1.0"
```

After the existing `METHODS_ANALYSIS_SYSTEM_PROMPT` in the System prompts section, add:

```python
ADJUDICATION_SYSTEM_PROMPT = """\
You are a senior biosecurity expert conducting contextual adjudication of a paper \
that has been flagged as potentially dual-use research of concern (DURC). You have \
access to the paper's abstract, methods section, the Stage 4 risk assessment, and \
enrichment data about the authors and institution.

Your task is to provide a contextual assessment considering:

1. **Author credibility**: Is the research group well-established in this field? \
Consider their h-index, citation counts, publication volume, and institutional affiliation.

2. **Institutional context**: Is the institution known for responsible dual-use research? \
Is it a major research university, government lab, or biodefense facility with oversight?

3. **Funding oversight**: Is the work funded by an agency with DURC review processes \
(e.g., NIH, BARDA, DTRA, BBSRC, Wellcome Trust)? Funded research at these agencies \
undergoes institutional biosafety committee (IBC) review.

4. **Research context**: Does the work duplicate or extend previously published dual-use \
research? Is this incremental in a well-governed research programme, or a concerning \
new direction from an unexpected source?

5. **Enrichment completeness**: If enrichment data is partial (some sources failed), \
note which sources were unavailable and how that limits your confidence. Reduce your \
confidence score accordingly.

You may adjust the risk tier UP or DOWN based on contextual factors. For example:
- A paper from a well-known virology lab with NIH funding and IBC approval described \
in the methods may warrant DOWNgrading from "high" to "medium".
- A paper with no institutional affiliation, no ORCID, and unusually detailed synthesis \
protocols may warrant UPgrading.

Always explain your reasoning clearly. The analyst reviewing your assessment needs to \
understand exactly why the tier was adjusted (or confirmed).

Use the adjudicate_paper tool to report your assessment."""
```

After the existing `ASSESS_DURC_RISK_TOOL` in the Tool schemas section, add:

```python
ADJUDICATE_PAPER_TOOL: dict = {
    "name": "adjudicate_paper",
    "description": "Provide contextual adjudication of a DURC-flagged paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "adjusted_risk_tier": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "adjusted_action": {
                "type": "string",
                "enum": ["archive", "monitor", "review", "escalate"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in this adjudication, reduced when enrichment is partial",
            },
            "partial_enrichment": {
                "type": "boolean",
                "description": "True if enrichment data was incomplete",
            },
            "missing_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Enrichment sources that failed",
            },
            "institutional_context": {
                "type": "string",
                "description": "Assessment of institutional/author credibility and oversight context",
            },
            "durc_oversight_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Evidence of DURC oversight "
                    "(IBC approval, DURC review, biosafety protocols)"
                ),
            },
            "adjustment_reasoning": {
                "type": "string",
                "description": "Why the risk tier was adjusted (or confirmed)",
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence contextual assessment",
            },
        },
        "required": [
            "adjusted_risk_tier",
            "adjusted_action",
            "confidence",
            "partial_enrichment",
            "missing_sources",
            "institutional_context",
            "durc_oversight_indicators",
            "adjustment_reasoning",
            "summary",
        ],
    },
}
```

After the existing `format_methods_analysis_message` in the User message formatting section, add:

```python
def format_adjudication_message(
    title: str,
    abstract: str,
    methods: str | None,
    stage2_result: dict,
    enrichment_data: dict,
    sources_failed: list[str],
) -> str:
    """Format the user message for Stage 5 adjudication."""
    import json

    parts = [
        f"Paper title: {title}",
        f"Abstract: {abstract}",
    ]

    if methods:
        parts.append(f"Methods section: {methods}")
    else:
        parts.append("Methods section: Not available.")

    parts.append(f"Stage 4 risk assessment: {json.dumps(stage2_result, indent=2)}")
    parts.append(f"Enrichment data: {json.dumps(enrichment_data, indent=2)}")

    if sources_failed:
        parts.append(
            f"WARNING: The following enrichment sources failed and their data is unavailable: "
            f"{', '.join(sources_failed)}. Reduce confidence accordingly."
        )

    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: All tests PASS (including both existing and new tests)

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/triage/prompts.py tests/test_prompts.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/triage/prompts.py tests/test_prompts.py
git commit -m "feat: add adjudication prompt, tool schema, and message formatter"
```

---

### Task 7: Adjudication module

**Files:**
- Create: `pipeline/triage/adjudication.py`
- Create: `tests/test_adjudication.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_adjudication.py`:

```python
"""Tests for pipeline.triage.adjudication -- Stage 5 Opus contextual review."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_adjudication_result(
    tier: str = "high",
    action: str = "review",
    confidence: float = 0.85,
    partial: bool = False,
    missing: list[str] | None = None,
):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={
            "adjusted_risk_tier": tier,
            "adjusted_action": action,
            "confidence": confidence,
            "partial_enrichment": partial,
            "missing_sources": missing or [],
            "institutional_context": "Well-established virology lab at MIT.",
            "durc_oversight_indicators": ["IBC approval cited", "NIH DURC review"],
            "adjustment_reasoning": "Confirmed high risk due to GoF methodology.",
            "summary": "This paper describes GoF research by a well-known lab. Risk confirmed.",
        },
        raw_response='{"test": true}',
        input_tokens=1000,
        output_tokens=500,
        cost_estimate_usd=0.05,
    )


class TestAdjudication:
    """Tests for run_adjudication."""

    async def test_paper_assessed_and_updated(self, db_session: AsyncSession):
        from pipeline.models import (
            AssessmentLog,
            PipelineStage,
            RecommendedAction,
            RiskTier,
        )
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="H5N1 GoF",
            abstract="We enhanced transmissibility.",
            methods_section="Serial passage in ferrets.",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high", "aggregate_score": 10},
            enrichment_data={
                "openalex": {"primary_institution": "MIT"},
                "_meta": {
                    "sources_succeeded": ["openalex", "semantic_scholar", "orcid"],
                    "sources_failed": [],
                },
            },
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_adjudication_result())

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.risk_tier == RiskTier.HIGH
        assert paper.recommended_action == RecommendedAction.REVIEW
        assert paper.stage3_result is not None
        assert paper.stage3_result["adjusted_risk_tier"] == "high"
        assert paper.stage3_result["institutional_context"] == "Well-established virology lab at MIT."

        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "adjudication"
        assert logs[0].model_used == "claude-opus-4-6"

    async def test_partial_enrichment_flag_propagated(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage, RiskTier, RecommendedAction
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Partial enrichment paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={
                "openalex": {"primary_institution": "MIT"},
                "_meta": {
                    "sources_succeeded": ["openalex"],
                    "sources_failed": ["semantic_scholar", "orcid"],
                },
            },
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_adjudication_result(
                partial=True,
                missing=["semantic_scholar", "orcid"],
                confidence=0.6,
            )
        )

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.stage3_result["partial_enrichment"] is True
        assert paper.stage3_result["confidence"] == 0.6

    async def test_llm_error_leaves_paper_at_methods_analysed(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage, RiskTier, RecommendedAction
        from pipeline.triage.adjudication import run_adjudication
        from pipeline.triage.llm import LLMResult

        paper = await insert_paper(
            db_session,
            title="Error paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )

        error_result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="Model refused",
        )
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=error_result)

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert paper.stage3_result is None

    async def test_below_threshold_paper_auto_advanced(self, db_session: AsyncSession):
        """Papers below the adjudication threshold are auto-advanced without Opus."""
        from pipeline.models import PipelineStage, RiskTier, RecommendedAction
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Low risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.MEDIUM,
            recommended_action=RecommendedAction.MONITOR,
            stage2_result={"risk_tier": "medium"},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock()

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        # Paper auto-advanced to ADJUDICATED without LLM call
        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.stage3_result is None
        # risk_tier and recommended_action remain from Stage 4
        assert paper.risk_tier == RiskTier.MEDIUM
        assert paper.recommended_action == RecommendedAction.MONITOR
        mock_llm.call_tool.assert_not_called()

    async def test_tier_threshold_filtering(self, db_session: AsyncSession):
        """Only papers at or above min_tier get Opus review."""
        from pipeline.models import PipelineStage, RiskTier, RecommendedAction
        from pipeline.triage.adjudication import run_adjudication

        high_paper = await insert_paper(
            db_session,
            title="High risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )
        low_paper = await insert_paper(
            db_session,
            title="Low risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.LOW,
            recommended_action=RecommendedAction.ARCHIVE,
            stage2_result={"risk_tier": "low"},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_adjudication_result())

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[high_paper, low_paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        # High paper gets Opus review
        assert high_paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert high_paper.stage3_result is not None

        # Low paper auto-advanced
        assert low_paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert low_paper.stage3_result is None
        assert low_paper.risk_tier == RiskTier.LOW

        # Only one LLM call (for the high paper)
        assert mock_llm.call_tool.call_count == 1

    async def test_risk_tier_downgrade(self, db_session: AsyncSession):
        """Opus can downgrade a paper's risk tier."""
        from pipeline.models import PipelineStage, RiskTier, RecommendedAction
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Downgraded paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_adjudication_result(tier="medium", action="monitor")
        )

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.risk_tier == RiskTier.MEDIUM
        assert paper.recommended_action == RecommendedAction.MONITOR

    async def test_empty_papers_list(self, db_session: AsyncSession):
        """Empty list does nothing."""
        from pipeline.triage.adjudication import run_adjudication

        mock_llm = AsyncMock()
        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[],
            model="claude-opus-4-6",
            min_tier="high",
        )
        mock_llm.call_tool.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_adjudication.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.triage.adjudication'`

- [ ] **Step 3: Implement the adjudication module**

Create `pipeline/triage/adjudication.py`:

```python
"""Stage 5: Adjudication -- Opus contextual review.

Processes papers that passed methods analysis and meet the configured
risk tier threshold. Provides contextual assessment using enrichment
data from OpenAlex, Semantic Scholar, and ORCID.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import (
    AssessmentLog,
    Paper,
    PipelineStage,
    RecommendedAction,
    RiskTier,
)
from pipeline.triage.llm import LLMClient, LLMResult
from pipeline.triage.prompts import (
    ADJUDICATE_PAPER_TOOL,
    ADJUDICATION_SYSTEM_PROMPT,
    ADJUDICATION_VERSION,
    format_adjudication_message,
)

log = structlog.get_logger()

# Maps string values from LLM output to model enums
_RISK_TIER_MAP = {
    "low": RiskTier.LOW,
    "medium": RiskTier.MEDIUM,
    "high": RiskTier.HIGH,
    "critical": RiskTier.CRITICAL,
}

_ACTION_MAP = {
    "archive": RecommendedAction.ARCHIVE,
    "monitor": RecommendedAction.MONITOR,
    "review": RecommendedAction.REVIEW,
    "escalate": RecommendedAction.ESCALATE,
}

# Tier ordering for threshold comparison
_TIER_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _tier_meets_threshold(tier: RiskTier | None, min_tier: str) -> bool:
    """Check if a paper's risk tier meets or exceeds the configured minimum."""
    if tier is None:
        return False
    tier_val = _TIER_ORDER.get(tier.value, 0)
    min_val = _TIER_ORDER.get(min_tier, 0)
    return tier_val >= min_val


def _create_assessment_log(
    session: AsyncSession,
    paper: Paper,
    llm_result: LLMResult,
    model: str,
    user_message: str,
) -> None:
    """Create an AssessmentLog entry from an LLM result."""
    session.add(
        AssessmentLog(
            paper_id=paper.id,
            stage="adjudication",
            model_used=model,
            prompt_version=ADJUDICATION_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


def _apply_result(paper: Paper, tool_input: dict) -> None:
    """Apply the adjudication result to the paper record."""
    paper.stage3_result = tool_input
    paper.risk_tier = _RISK_TIER_MAP.get(tool_input.get("adjusted_risk_tier", ""))
    paper.recommended_action = _ACTION_MAP.get(tool_input.get("adjusted_action", ""))
    paper.pipeline_stage = PipelineStage.ADJUDICATED


async def run_adjudication(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    min_tier: str,
) -> None:
    """Run Stage 5 adjudication on a list of papers.

    Papers below min_tier are auto-advanced to ADJUDICATED without Opus review.
    Papers at or above min_tier get full Opus contextual assessment.
    """
    if not papers:
        return

    adjudicated_count = 0
    auto_advanced_count = 0

    for paper in papers:
        if not _tier_meets_threshold(paper.risk_tier, min_tier):
            # Auto-advance below-threshold papers
            paper.pipeline_stage = PipelineStage.ADJUDICATED
            auto_advanced_count += 1
            log.info(
                "adjudication_auto_advanced",
                paper_id=str(paper.id),
                risk_tier=paper.risk_tier.value if paper.risk_tier else None,
                min_tier=min_tier,
            )
            await session.flush()
            continue

        # Extract enrichment metadata
        enrichment_data = paper.enrichment_data or {}
        meta = enrichment_data.get("_meta", {})
        sources_failed = meta.get("sources_failed", [])

        user_msg = format_adjudication_message(
            title=paper.title,
            abstract=paper.abstract or "",
            methods=paper.methods_section,
            stage2_result=paper.stage2_result or {},
            enrichment_data=enrichment_data,
            sources_failed=sources_failed,
        )

        llm_result = await llm_client.call_tool(
            model=model,
            system_prompt=ADJUDICATION_SYSTEM_PROMPT,
            user_message=user_msg,
            tool=ADJUDICATE_PAPER_TOOL,
        )

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning(
                "adjudication_error",
                paper_id=str(paper.id),
                error=llm_result.error,
            )
            continue

        _apply_result(paper, llm_result.tool_input)
        adjudicated_count += 1
        log.info(
            "adjudication_complete",
            paper_id=str(paper.id),
            adjusted_tier=llm_result.tool_input.get("adjusted_risk_tier"),
            confidence=llm_result.tool_input.get("confidence"),
        )
        await session.flush()

    log.info(
        "adjudication_run_complete",
        total=len(papers),
        adjudicated=adjudicated_count,
        auto_advanced=auto_advanced_count,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_adjudication.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/triage/adjudication.py tests/test_adjudication.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/triage/adjudication.py tests/test_adjudication.py
git commit -m "feat: add Stage 5 Opus adjudication with tier threshold filtering"
```

---

### Task 8: Orchestrator

**Files:**
- Create: `pipeline/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator.py`:

```python
"""Tests for pipeline.orchestrator -- daily pipeline orchestrator."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import insert_paper


class TestRunDailyPipeline:
    """Tests for run_daily_pipeline."""

    async def test_stages_run_in_order(self, db_engine, db_session: AsyncSession):
        from pipeline.orchestrator import run_daily_pipeline

        call_order = []

        async def mock_ingest(session, settings, from_date, to_date):
            call_order.append("ingest")
            return []

        async def mock_dedup(session, papers):
            call_order.append("dedup")
            return papers, 0

        async def mock_coarse(session, llm, papers, use_batch, model, threshold):
            call_order.append("coarse_filter")
            return papers

        async def mock_fulltext(session, paper, settings):
            call_order.append("fulltext")

        async def mock_methods(session, llm, papers, use_batch, model):
            call_order.append("methods_analysis")

        async def mock_enrich(session, papers, settings):
            call_order.append("enrichment")
            return papers

        async def mock_adjudicate(session, llm, papers, model, min_tier):
            call_order.append("adjudication")

        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        with (
            patch("pipeline.orchestrator._run_ingest", mock_ingest),
            patch("pipeline.orchestrator._run_dedup", mock_dedup),
            patch("pipeline.orchestrator.run_coarse_filter", mock_coarse),
            patch("pipeline.orchestrator.retrieve_full_text", mock_fulltext),
            patch("pipeline.orchestrator.run_methods_analysis", mock_methods),
            patch("pipeline.orchestrator._run_enrichment", mock_enrich),
            patch("pipeline.orchestrator.run_adjudication", mock_adjudicate),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        assert call_order == [
            "ingest",
            "dedup",
            "coarse_filter",
            "fulltext",
            "methods_analysis",
            "enrichment",
            "adjudication",
        ]
        assert stats.finished_at is not None

    async def test_stats_populated(self, db_engine, db_session: AsyncSession):
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.retrieve_full_text", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        assert stats.started_at is not None
        assert stats.finished_at is not None
        assert isinstance(stats.errors, list)
        assert isinstance(stats.total_cost_usd, float)

    async def test_pipeline_run_row_written(self, db_engine, db_session: AsyncSession):
        from pipeline.models import PipelineRun
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.retrieve_full_text", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        # Check PipelineRun row was written
        async with session_factory() as check_session:
            result = await check_session.execute(select(PipelineRun))
            runs = result.scalars().all()
            assert len(runs) == 1
            assert runs[0].trigger == "manual"
            assert runs[0].finished_at is not None

    async def test_stage_failure_isolation(self, db_engine, db_session: AsyncSession):
        """A failure in one stage should not prevent later stages."""
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        async def failing_ingest(session, settings, from_date, to_date):
            raise RuntimeError("Ingest exploded")

        with (
            patch("pipeline.orchestrator._run_ingest", failing_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.retrieve_full_text", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        # Pipeline completed despite ingest failure
        assert stats.finished_at is not None
        assert len(stats.errors) >= 1
        assert "Ingest exploded" in stats.errors[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.orchestrator'`

- [ ] **Step 3: Implement the orchestrator**

Create `pipeline/orchestrator.py`:

```python
"""Daily pipeline orchestrator -- ties all stages together.

Usage:
    stats = await run_daily_pipeline()

Or with custom settings/session:
    stats = await run_daily_pipeline(settings=my_settings, session_factory=my_factory)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipeline.enrichment.enricher import enrich_paper
from pipeline.fulltext.retriever import retrieve_full_text
from pipeline.ingest.biorxiv import BiorxivClient
from pipeline.ingest.dedup import DedupEngine
from pipeline.ingest.europepmc import EuropepmcClient
from pipeline.ingest.pubmed import PubmedClient
from pipeline.models import Paper, PipelineRun, PipelineStage
from pipeline.triage.adjudication import run_adjudication
from pipeline.triage.coarse_filter import run_coarse_filter
from pipeline.triage.llm import LLMClient
from pipeline.triage.methods_analysis import run_methods_analysis

log = structlog.get_logger()


@dataclass
class PipelineRunStats:
    """Statistics from a single pipeline run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    papers_ingested: int = 0
    papers_after_dedup: int = 0
    papers_coarse_passed: int = 0
    papers_fulltext_retrieved: int = 0
    papers_methods_analysed: int = 0
    papers_enriched: int = 0
    papers_adjudicated: int = 0
    errors: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0


async def run_daily_pipeline(
    settings=None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    trigger: str = "manual",
) -> PipelineRunStats:
    """Run the complete daily triage pipeline.

    Args:
        settings: Pipeline settings. If None, loads from environment.
        session_factory: SQLAlchemy async session factory. If None, creates one.
        trigger: "scheduled" or "manual" -- recorded in PipelineRun.
    """
    if settings is None:
        from pipeline.config import get_settings

        settings = get_settings()

    if session_factory is None:
        from pipeline.db import make_engine, make_session_factory

        engine = make_engine(settings.database_url.get_secret_value())
        session_factory = make_session_factory(engine)

    stats = PipelineRunStats()
    llm_client = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())

    # Create PipelineRun record
    run_record = PipelineRun(
        started_at=stats.started_at,
        trigger=trigger,
    )
    async with session_factory() as session:
        session.add(run_record)
        await session.commit()
    run_id = run_record.id

    # Date range: last 2 days
    to_date = date.today()
    from_date = to_date - timedelta(days=2)

    async with session_factory() as session:
        # Stage 1: Ingest
        ingested_papers: list[Paper] = []
        try:
            ingested_papers = await _run_ingest(session, settings, from_date, to_date)
            stats.papers_ingested = len(ingested_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Ingest: {exc}")
            log.error("pipeline_ingest_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 2: Dedup
        non_dup_papers: list[Paper] = []
        try:
            non_dup_papers, dup_count = await _run_dedup(session, ingested_papers)
            stats.papers_after_dedup = len(non_dup_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Dedup: {exc}")
            log.error("pipeline_dedup_error", error=str(exc), exc_info=True)
            non_dup_papers = ingested_papers
            await session.rollback()

    async with session_factory() as session:
        # Stage 3: Coarse filter
        # Query papers at INGESTED stage (non-duplicates)
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.INGESTED,
                Paper.is_duplicate_of.is_(None),
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            ingested = result.scalars().all()

            passed = await run_coarse_filter(
                session=session,
                llm_client=llm_client,
                papers=list(ingested),
                use_batch=settings.use_batch_api,
                model=settings.stage1_model,
                threshold=settings.coarse_filter_threshold,
            )
            stats.papers_coarse_passed = len(passed)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Coarse filter: {exc}")
            log.error("pipeline_coarse_filter_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 4: Full-text retrieval
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.COARSE_FILTERED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            coarse_passed = result.scalars().all()

            for paper in coarse_passed:
                await retrieve_full_text(session, paper, settings)
            stats.papers_fulltext_retrieved = sum(
                1 for p in coarse_passed if p.full_text_retrieved
            )
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Full-text retrieval: {exc}")
            log.error("pipeline_fulltext_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 5: Methods analysis
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            fulltext_papers = list(result.scalars().all())

            await run_methods_analysis(
                session=session,
                llm_client=llm_client,
                papers=fulltext_papers,
                use_batch=settings.use_batch_api,
                model=settings.stage2_model,
            )
            stats.papers_methods_analysed = len(fulltext_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Methods analysis: {exc}")
            log.error("pipeline_methods_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 6: Enrichment
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            methods_papers = list(result.scalars().all())

            enriched = await _run_enrichment(session, methods_papers, settings)
            stats.papers_enriched = len(enriched)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Enrichment: {exc}")
            log.error("pipeline_enrichment_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 7: Adjudication
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            to_adjudicate = list(result.scalars().all())

            await run_adjudication(
                session=session,
                llm_client=llm_client,
                papers=to_adjudicate,
                model=settings.stage3_model,
                min_tier=settings.adjudication_min_tier,
            )
            stats.papers_adjudicated = len(to_adjudicate)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Adjudication: {exc}")
            log.error("pipeline_adjudication_error", error=str(exc), exc_info=True)
            await session.rollback()

    stats.finished_at = datetime.now(timezone.utc)

    # Update PipelineRun record
    async with session_factory() as session:
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        result = await session.execute(stmt)
        run_record = result.scalar_one()
        run_record.finished_at = stats.finished_at
        run_record.papers_ingested = stats.papers_ingested
        run_record.papers_after_dedup = stats.papers_after_dedup
        run_record.papers_coarse_passed = stats.papers_coarse_passed
        run_record.papers_fulltext_retrieved = stats.papers_fulltext_retrieved
        run_record.papers_methods_analysed = stats.papers_methods_analysed
        run_record.papers_enriched = stats.papers_enriched
        run_record.papers_adjudicated = stats.papers_adjudicated
        run_record.errors = stats.errors if stats.errors else None
        run_record.total_cost_usd = stats.total_cost_usd
        await session.commit()

    log.info(
        "pipeline_complete",
        papers_ingested=stats.papers_ingested,
        papers_adjudicated=stats.papers_adjudicated,
        errors=len(stats.errors),
        duration_s=(stats.finished_at - stats.started_at).total_seconds(),
    )

    return stats


async def _run_ingest(
    session: AsyncSession,
    settings,
    from_date: date,
    to_date: date,
) -> list[Paper]:
    """Run all ingest clients and return new papers."""
    papers: list[Paper] = []

    # bioRxiv
    async with BiorxivClient(
        server="biorxiv", request_delay=settings.biorxiv_request_delay
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # medRxiv
    async with BiorxivClient(
        server="medrxiv", request_delay=settings.biorxiv_request_delay
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # Europe PMC
    async with EuropepmcClient(
        request_delay=settings.europepmc_request_delay,
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # PubMed
    async with PubmedClient(
        api_key=settings.ncbi_api_key,
        request_delay=settings.pubmed_request_delay,
        query_mode=settings.pubmed_query_mode,
        mesh_query=settings.pubmed_mesh_query,
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    await session.flush()
    log.info("ingest_complete", count=len(papers))
    return papers


async def _run_dedup(
    session: AsyncSession,
    papers: list[Paper],
) -> tuple[list[Paper], int]:
    """Run dedup on new papers. Returns (non_duplicates, duplicate_count)."""
    engine = DedupEngine(session)
    non_dups: list[Paper] = []
    dup_count = 0

    for paper in papers:
        record = {
            "doi": paper.doi,
            "title": paper.title,
            "authors": paper.authors,
            "posted_date": paper.posted_date,
        }
        result = await engine.check(record)
        if result.is_duplicate:
            paper.is_duplicate_of = result.duplicate_of
            await engine.record_duplicate(
                canonical_id=result.duplicate_of,
                member_id=paper.id,
                result=result,
            )
            dup_count += 1
        else:
            non_dups.append(paper)

    await session.flush()
    log.info("dedup_complete", total=len(papers), duplicates=dup_count)
    return non_dups, dup_count


async def _run_enrichment(
    session: AsyncSession,
    papers: list[Paper],
    settings,
) -> list[Paper]:
    """Run enrichment on papers and store results."""
    enriched: list[Paper] = []

    for paper in papers:
        try:
            result = await enrich_paper(paper, settings)
            paper.enrichment_data = {
                **result.data,
                "_meta": {
                    "sources_succeeded": result.sources_succeeded,
                    "sources_failed": result.sources_failed,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            enriched.append(paper)
        except Exception as exc:
            log.warning("enrichment_paper_error", paper_id=str(paper.id), error=str(exc))

    await session.flush()
    log.info("enrichment_stage_complete", total=len(papers), enriched=len(enriched))
    return enriched
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/orchestrator.py tests/test_orchestrator.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add daily pipeline orchestrator with stage isolation and PipelineRun tracking"
```

---

### Task 9: Scheduler

**Files:**
- Create: `pipeline/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scheduler.py`:

```python
"""Tests for pipeline.scheduler -- APScheduler wrapper for daily pipeline runs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPipelineScheduler:
    """Tests for PipelineScheduler."""

    def _make_settings(self):
        mock_settings = MagicMock()
        mock_settings.daily_run_hour = 6
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        return mock_settings

    def test_scheduler_creates_job(self):
        """Scheduler initialises with a cron job at the configured hour."""
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        assert scheduler._settings.daily_run_hour == 6
        assert scheduler._paused is False

    async def test_get_status_before_start(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        status = scheduler.get_status()
        assert status["running"] is False
        assert status["paused"] is False
        assert status["last_run_stats"] is None

    async def test_trigger_run_executes(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        mock_stats = MagicMock()
        with patch(
            "pipeline.scheduler.run_daily_pipeline",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            stats = await scheduler.trigger_run()

        assert stats is mock_stats
        assert scheduler._last_run_stats is mock_stats

    async def test_update_schedule_changes_hour(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        await scheduler.update_schedule(12, 30)
        assert scheduler._hour == 12
        assert scheduler._minute == 30

    async def test_pause_and_resume(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        await scheduler.pause()
        assert scheduler._paused is True
        status = scheduler.get_status()
        assert status["paused"] is True

        await scheduler.resume()
        assert scheduler._paused is False
        status = scheduler.get_status()
        assert status["paused"] is False

    async def test_get_status_after_run(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        mock_stats = MagicMock()
        with patch(
            "pipeline.scheduler.run_daily_pipeline",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            await scheduler.trigger_run()

        status = scheduler.get_status()
        assert status["last_run_stats"] is mock_stats
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'pipeline.scheduler'`

- [ ] **Step 3: Implement the scheduler**

Create `pipeline/scheduler.py`:

```python
"""APScheduler 3.x wrapper for daily pipeline execution.

Usage:
    scheduler = PipelineScheduler(settings)
    await scheduler.start()  # Blocks forever, runs daily

Or for programmatic control:
    scheduler = PipelineScheduler(settings)
    stats = await scheduler.trigger_run()  # One-shot
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.orchestrator import PipelineRunStats, run_daily_pipeline

log = structlog.get_logger()


class PipelineScheduler:
    """Manages scheduled and on-demand pipeline runs."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._hour = settings.daily_run_hour
        self._minute = 0
        self._scheduler: AsyncIOScheduler | None = None
        self._paused = False
        self._running = False
        self._last_run_stats: PipelineRunStats | None = None
        self._last_run_time: datetime | None = None

    async def start(self) -> None:
        """Start the scheduler with the configured daily cron. Blocks forever."""
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=CronTrigger(hour=self._hour, minute=self._minute),
            id="daily_pipeline",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        log.info(
            "scheduler_started",
            hour=self._hour,
            minute=self._minute,
        )

        # Block forever (until stop is called or process exits)
        try:
            while self._running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            await self.stop()

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        self._running = False
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        log.info("scheduler_stopped")

    async def trigger_run(self) -> PipelineRunStats:
        """Trigger an immediate pipeline run."""
        log.info("manual_run_triggered")
        stats = await self._run_pipeline(trigger="manual")
        return stats

    async def update_schedule(self, hour: int, minute: int = 0) -> None:
        """Change the daily run time."""
        self._hour = hour
        self._minute = minute
        if self._scheduler:
            self._scheduler.reschedule_job(
                "daily_pipeline",
                trigger=CronTrigger(hour=hour, minute=minute),
            )
        log.info("schedule_updated", hour=hour, minute=minute)

    async def pause(self) -> None:
        """Pause scheduled runs (manual runs still allowed)."""
        self._paused = True
        if self._scheduler:
            self._scheduler.pause_job("daily_pipeline")
        log.info("scheduler_paused")

    async def resume(self) -> None:
        """Resume scheduled runs."""
        self._paused = False
        if self._scheduler:
            self._scheduler.resume_job("daily_pipeline")
        log.info("scheduler_resumed")

    def get_status(self) -> dict:
        """Return scheduler state for the dashboard."""
        next_run = None
        if self._scheduler and not self._paused:
            job = self._scheduler.get_job("daily_pipeline")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        return {
            "running": self._running,
            "paused": self._paused,
            "next_run_time": next_run,
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
            "last_run_stats": self._last_run_stats,
        }

    async def _run_pipeline(self, trigger: str = "scheduled") -> PipelineRunStats:
        """Execute the pipeline and update internal state."""
        self._last_run_time = datetime.now(timezone.utc)
        try:
            stats = await run_daily_pipeline(
                settings=self._settings,
                trigger=trigger,
            )
            self._last_run_stats = stats
            log.info(
                "pipeline_run_complete",
                trigger=trigger,
                papers_ingested=stats.papers_ingested,
                errors=len(stats.errors),
            )
            return stats
        except Exception as exc:
            log.error("pipeline_run_failed", trigger=trigger, error=str(exc), exc_info=True)
            error_stats = PipelineRunStats()
            error_stats.errors = [str(exc)]
            error_stats.finished_at = datetime.now(timezone.utc)
            self._last_run_stats = error_stats
            return error_stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check pipeline/scheduler.py tests/test_scheduler.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add pipeline/scheduler.py tests/test_scheduler.py
git commit -m "feat: add APScheduler-based pipeline scheduler with pause/resume/trigger"
```

---

### Task 10: Entry point

**Files:**
- Create: `pipeline/__main__.py`

- [ ] **Step 1: Write a simple import test**

Run: `uv run python -c "import pipeline.orchestrator; print('OK')"` to verify the module is importable.

Expected: `OK` (or an error if something is wrong with imports -- fix if needed)

- [ ] **Step 2: Create the entry point**

Create `pipeline/__main__.py`:

```python
"""Entry point for the DURC triage pipeline.

Usage:
    python -m pipeline              # One-shot run
    python -m pipeline --schedule   # Long-lived scheduled mode
"""

from __future__ import annotations

import asyncio
import sys

import structlog

log = structlog.get_logger()


def main() -> None:
    """Parse args and run the pipeline in the appropriate mode."""
    if "--schedule" in sys.argv:
        _run_scheduled()
    else:
        _run_oneshot()


def _run_oneshot() -> None:
    """Execute a single pipeline run and exit."""
    from pipeline.orchestrator import run_daily_pipeline

    log.info("pipeline_oneshot_start")
    stats = asyncio.run(run_daily_pipeline(trigger="manual"))
    log.info(
        "pipeline_oneshot_complete",
        papers_ingested=stats.papers_ingested,
        papers_adjudicated=stats.papers_adjudicated,
        errors=len(stats.errors),
    )
    if stats.errors:
        log.warning("pipeline_errors", errors=stats.errors)


def _run_scheduled() -> None:
    """Start the scheduler for continuous daily operation."""
    from pipeline.config import get_settings
    from pipeline.scheduler import PipelineScheduler

    settings = get_settings()
    scheduler = PipelineScheduler(settings)
    log.info("pipeline_scheduled_start", hour=settings.daily_run_hour)
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the entry point syntax**

Run: `uv run python -c "import pipeline.__main__; print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 4: Lint**

Run: `uv run ruff check pipeline/__main__.py`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add pipeline/__main__.py
git commit -m "feat: add pipeline __main__ entry point with one-shot and schedule modes"
```

---

### Task 11: Config test update

**Files:**
- Verify: `tests/test_config.py`

This task ensures the `test_settings_sp3_defaults` test added in Task 1 is present and passes alongside all other config tests.

- [ ] **Step 1: Run all config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: All tests PASS, including:
- `test_settings_loads_from_env`
- `test_settings_defaults`
- `test_secret_str_redacts_in_repr`
- `test_settings_phase2_defaults`
- `test_settings_sp2_defaults`
- `test_settings_sp3_defaults`

- [ ] **Step 2: Verify no additional tests needed**

The SP3 config test was already added in Task 1. Confirm it covers all new fields: `openalex_request_delay`, `semantic_scholar_request_delay`, `orcid_request_delay`, `adjudication_min_tier`.

No commit needed for this task -- it is a verification step.

---

### Task 12: Final integration verification

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. Count should include tests from:
- `test_config.py` (6 tests)
- `test_models.py` (3+ tests)
- `test_db.py`
- `test_ingest.py`
- `test_dedup.py`
- `test_europepmc.py`
- `test_pubmed.py`
- `test_prompts.py` (with new adjudication tests)
- `test_llm.py`
- `test_coarse_filter.py`
- `test_jats_parser.py`
- `test_html_parser.py`
- `test_unpaywall.py`
- `test_retriever.py`
- `test_methods_analysis.py`
- `test_openalex.py` (new)
- `test_semantic_scholar.py` (new)
- `test_orcid.py` (new)
- `test_enricher.py` (new)
- `test_adjudication.py` (new)
- `test_orchestrator.py` (new)
- `test_scheduler.py` (new)

- [ ] **Step 2: Lint check**

Run: `uv run ruff check pipeline/ tests/`
Expected: No errors

- [ ] **Step 3: Verify all imports are clean**

Run: `uv run python -c "from pipeline.enrichment.openalex import OpenAlexClient; from pipeline.enrichment.semantic_scholar import SemanticScholarClient; from pipeline.enrichment.orcid import OrcidClient; from pipeline.enrichment.enricher import enrich_paper, EnrichmentResult; from pipeline.triage.adjudication import run_adjudication; from pipeline.orchestrator import run_daily_pipeline, PipelineRunStats; from pipeline.scheduler import PipelineScheduler; from pipeline.models import PipelineRun; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 4: Verify file structure**

Run: `find pipeline/enrichment -type f | sort && find pipeline/triage -name 'adjudication.py' && ls pipeline/orchestrator.py pipeline/scheduler.py pipeline/__main__.py`

Expected output:
```
pipeline/enrichment/__init__.py
pipeline/enrichment/enricher.py
pipeline/enrichment/openalex.py
pipeline/enrichment/orcid.py
pipeline/enrichment/semantic_scholar.py
pipeline/triage/adjudication.py
pipeline/orchestrator.py
pipeline/scheduler.py
pipeline/__main__.py
```

No commit needed -- this is a verification step.

---

### Task 13: Memory notes

- [ ] **Step 1: Record project memory about SP3 implementation**

Save the following notes for future reference during Phase 3 dashboard implementation:

**Enrichment sources implemented:**
- OpenAlex: author/institution metadata, topics, citation counts, funder names. Client at `pipeline/enrichment/openalex.py`.
- Semantic Scholar: paper TLDRs, citation counts, author h-index. Client at `pipeline/enrichment/semantic_scholar.py`.
- ORCID: author identity, employment history, education. Client at `pipeline/enrichment/orcid.py`.
- Enricher orchestrator at `pipeline/enrichment/enricher.py` merges all three sources with graceful degradation.

**Dashboard UI requirements for configurable settings:**
- `adjudication_min_tier` -- dropdown: low, medium, high, critical
- `use_batch_api` -- toggle switch
- `coarse_filter_threshold` -- slider 0.0-1.0
- `pubmed_query_mode` -- dropdown: all, mesh_filtered
- `daily_run_hour` -- time picker (calls `PipelineScheduler.update_schedule()`)
- Rate limit delays (`openalex_request_delay`, `semantic_scholar_request_delay`, `orcid_request_delay`, etc.) -- numeric inputs
- Model selection (`stage1_model`, `stage2_model`, `stage3_model`) -- dropdowns
- Pipeline control: Pause/Resume toggle, "Run Now" button, status display, run history table (from `pipeline_runs` table)

**Pipeline run tracking:**
- `PipelineRun` model in `pipeline/models.py` stores run history
- `PipelineRunStats` dataclass in `pipeline/orchestrator.py` provides in-memory stats
- `PipelineScheduler.get_status()` returns current scheduler state for the dashboard

- [ ] **Step 2: Final commit (if any uncommitted changes remain)**

```bash
git status
# If there are uncommitted changes:
git add -A
git commit -m "chore: SP3 implementation complete -- enrichment, adjudication, orchestrator, scheduler"
```
