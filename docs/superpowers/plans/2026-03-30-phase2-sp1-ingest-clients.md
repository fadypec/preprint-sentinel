# Phase 2 Sub-project 1: Ingest Clients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Europe PMC and PubMed ingest clients to the pipeline, following the established async client pattern from `BiorxivClient`.

**Architecture:** Both clients are async context managers wrapping `httpx.AsyncClient`, exposing `fetch_papers(from_date, to_date) -> AsyncGenerator[dict]` that handles pagination internally. Europe PMC uses cursor-based pagination; PubMed uses a two-step search-then-fetch via E-utilities with XML parsing. PubMed supports a configurable toggle between "all" (comprehensive) and "mesh_filtered" (cost-conscious) query modes.

**Tech Stack:** Python 3.11+, httpx, lxml (XML parsing), structlog, respx (test mocks), pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-30-phase2-sp1-ingest-clients-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pipeline/config.py` | **Modify:** Add `europepmc_request_delay`, `pubmed_query_mode`, `pubmed_mesh_query` settings |
| `pipeline/ingest/europepmc.py` | **Create:** Europe PMC async client with cursor-based pagination |
| `pipeline/ingest/pubmed.py` | **Create:** PubMed E-utilities async client with esearch+efetch, XML parsing, query modes |
| `tests/conftest.py` | **Modify:** Add Europe PMC record factories |
| `tests/fixtures/sample_europepmc.json` | **Create:** 5 realistic Europe PMC search results |
| `tests/fixtures/sample_pubmed.xml` | **Create:** 5 realistic PubmedArticle XML records |
| `tests/test_europepmc.py` | **Create:** Europe PMC client tests (normalisation, fetch, retry) |
| `tests/test_pubmed.py` | **Create:** PubMed client tests (XML parsing, search, fetch, retry, query modes) |
| `tests/test_config.py` | **Modify:** Add tests for new config fields |

---

### Task 1: Configuration updates

**Files:**
- Modify: `pipeline/config.py:39-42`
- Modify: `tests/test_config.py:16-28`

- [ ] **Step 1: Write the failing test for new config defaults**

Add a test to `tests/test_config.py` that checks the three new fields have correct defaults:

```python
def test_settings_phase2_defaults(monkeypatch):
    """Phase 2 config fields have sensible defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    from pipeline.config import Settings

    s = Settings()
    assert s.europepmc_request_delay == 1.0
    assert s.pubmed_query_mode == "all"
    assert "virology[MeSH]" in s.pubmed_mesh_query
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_settings_phase2_defaults -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'europepmc_request_delay'`

- [ ] **Step 3: Add new fields to Settings**

In `pipeline/config.py`, add after the existing `pubmed_request_delay` field (line ~42):

```python
    # Europe PMC
    europepmc_request_delay: float = 1.0

    # PubMed query mode
    pubmed_query_mode: str = "all"  # "all" or "mesh_filtered"
    pubmed_mesh_query: str = (
        '(virology[MeSH] OR microbiology[MeSH] OR "synthetic biology"[MeSH] OR '
        '"genetic engineering"[MeSH] OR "gain of function"[tiab] OR '
        '"gain-of-function"[tiab] OR "directed evolution"[tiab] OR '
        '"reverse genetics"[tiab] OR "gene drive"[tiab] OR "gene drives"[tiab] OR '
        '"select agent"[tiab] OR "select agents"[tiab] OR '
        '"dual use"[tiab] OR "dual-use"[tiab] OR '
        '"pathogen enhancement"[tiab] OR "immune evasion"[tiab] OR '
        '"host range"[tiab] OR "transmissibility"[tiab] OR '
        '"virulence factor"[tiab] OR "virulence factors"[tiab] OR '
        'toxins[MeSH] OR "biological warfare"[MeSH] OR "biodefense"[MeSH] OR '
        'CRISPR[tiab] OR "base editing"[tiab] OR '
        '"pandemic preparedness"[tiab] OR "pandemic pathogen"[tiab] OR '
        '"biosafety level"[tiab] OR "BSL-3"[tiab] OR "BSL-4"[tiab] OR '
        'prions[MeSH] OR "mirror life"[tiab] OR "xenobiology"[tiab] OR '
        '"de novo protein design"[tiab] OR "protein design"[tiab] OR '
        '"aerosol transmission"[tiab] OR "airborne transmission"[tiab])'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: All 4 tests PASS (3 existing + 1 new)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/config.py tests/test_config.py
uv run ruff format pipeline/config.py tests/test_config.py
git add pipeline/config.py tests/test_config.py
git commit -m "feat: add Europe PMC and PubMed config fields"
```

---

### Task 2: Europe PMC fixture data and conftest helpers

**Files:**
- Create: `tests/fixtures/sample_europepmc.json`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create sample Europe PMC fixture file**

Create `tests/fixtures/sample_europepmc.json`:

```json
{
  "hitCount": 5,
  "nextCursorMark": "AoE1234567",
  "resultList": {
    "result": [
      {
        "id": "PPR100001",
        "doi": "10.1101/2026.03.01.123456",
        "title": "Gain-of-function analysis of H5N1 transmissibility in ferrets",
        "authorString": "Smith J, Jones A, Williams BC",
        "firstPublicationDate": "2026-03-01",
        "abstractText": "We describe experiments enhancing airborne transmissibility of H5N1 in ferret models.",
        "source": "PPR",
        "journalInfo": {"journal": {"title": "bioRxiv"}}
      },
      {
        "id": "PPR100002",
        "doi": "10.1101/2026.03.02.654321",
        "title": "CRISPR-based gene drive for mosquito population suppression",
        "authorString": "Chen W, Zhang L",
        "firstPublicationDate": "2026-03-02",
        "abstractText": "A self-limiting gene drive construct targeting <i>Anopheles gambiae</i> fertility genes.",
        "source": "PPR",
        "journalInfo": {"journal": {"title": "bioRxiv"}}
      },
      {
        "id": "PPR100003",
        "doi": "10.21203/rs.3.rs-9999999/v1",
        "title": "Novel reverse genetics system for Nipah virus",
        "authorString": "Patel S, Kumar R, Das A",
        "firstPublicationDate": "2026-03-03",
        "abstractText": "We report a simplified plasmid-based reverse genetics system for rescue of recombinant Nipah virus.",
        "source": "PPR",
        "journalInfo": {"journal": {"title": "Research Square"}}
      },
      {
        "id": "PPR100004",
        "doi": null,
        "title": "Characterisation of a novel bat coronavirus with broad ACE2 tropism",
        "authorString": "Lee H, Park J",
        "firstPublicationDate": "2026-03-01",
        "abstractText": "Metagenomic surveillance identified a novel betacoronavirus in Rhinolophus bats.",
        "source": "PPR",
        "journalInfo": {"journal": {"title": "Preprints.org"}}
      },
      {
        "id": "PPR100005",
        "doi": "10.1101/2026.03.05.111111",
        "title": "Structural basis of immune evasion by engineered influenza neuraminidase",
        "authorString": "Brown T",
        "firstPublicationDate": "2026-03-05",
        "abstractText": "Directed evolution of N1 neuraminidase yielded variants escaping all approved neuraminidase inhibitors.",
        "source": "PPR",
        "journalInfo": {"journal": {"title": "bioRxiv"}}
      }
    ]
  }
}
```

- [ ] **Step 2: Add Europe PMC conftest helpers**

Add to `tests/conftest.py` after the existing `make_collection` function:

```python
# ---------------------------------------------------------------------------
# Europe PMC record factories
# ---------------------------------------------------------------------------


def make_europepmc_record(
    ppr_id: str = "PPR100001",
    doi: str | None = "10.1101/2026.03.01.123456",
    title: str = "Test Europe PMC Paper",
    author_string: str = "Smith J, Jones A",
    first_pub_date: str = "2026-03-01",
    abstract: str = "A test abstract from Europe PMC.",
    source: str = "PPR",
) -> dict:
    """Create a raw record matching the Europe PMC search API format."""
    record: dict = {
        "id": ppr_id,
        "title": title,
        "authorString": author_string,
        "firstPublicationDate": first_pub_date,
        "abstractText": abstract,
        "source": source,
    }
    if doi is not None:
        record["doi"] = doi
    return record


def make_europepmc_response(
    results: list[dict],
    hit_count: int | None = None,
    next_cursor: str = "AoE_next",
) -> dict:
    """Wrap Europe PMC records in the API response envelope."""
    if hit_count is None:
        hit_count = len(results)
    return {
        "hitCount": hit_count,
        "nextCursorMark": next_cursor,
        "resultList": {"result": results},
    }
```

- [ ] **Step 3: Verify conftest imports still work**

Run: `uv run pytest tests/test_config.py -v`
Expected: All tests still PASS (conftest changes are additive)

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix tests/conftest.py
uv run ruff format tests/conftest.py
git add tests/fixtures/sample_europepmc.json tests/conftest.py
git commit -m "feat: add Europe PMC fixture data and conftest factories"
```

---

### Task 3: Europe PMC client — field normalisation

**Files:**
- Create: `pipeline/ingest/europepmc.py`
- Create: `tests/test_europepmc.py`

- [ ] **Step 1: Write failing normalisation tests**

Create `tests/test_europepmc.py`:

```python
"""Tests for pipeline.ingest.europepmc — Europe PMC API client."""

from __future__ import annotations

from datetime import date

from tests.conftest import make_europepmc_record


class TestNormalise:
    """Tests for EuropepmcClient._normalise field mapping."""

    def _make_client(self):
        from pipeline.ingest.europepmc import EuropepmcClient

        return EuropepmcClient(request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        raw = make_europepmc_record(
            doi="10.1101/2026.03.15.500001",
            title="  Test Title With Spaces  ",
            author_string="Smith J, Jones A, Brown BC",
            first_pub_date="2026-03-15",
        )
        result = client._normalise(raw)

        assert result["doi"] == "10.1101/2026.03.15.500001"
        assert result["title"] == "Test Title With Spaces"  # stripped
        assert result["authors"] == [
            {"name": "Smith J"},
            {"name": "Jones A"},
            {"name": "Brown BC"},
        ]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "europepmc"
        assert result["version"] == 1

    def test_html_entity_decoding_in_abstract(self):
        client = self._make_client()
        raw = make_europepmc_record(
            abstract="The 1.8 &Aring; structure shows &lt;50% occupancy &amp; high B-factors."
        )
        result = client._normalise(raw)
        assert "\u00c5" in result["abstract"]  # Angstrom symbol decoded
        assert "<50%" in result["abstract"]
        assert "& high" in result["abstract"]

    def test_fields_not_available_from_search(self):
        """Europe PMC search doesn't provide these fields — all should be None."""
        client = self._make_client()
        raw = make_europepmc_record()
        result = client._normalise(raw)
        assert result["corresponding_author"] is None
        assert result["corresponding_institution"] is None
        assert result["subject_category"] is None
        assert result["full_text_url"] is None

    def test_empty_author_string(self):
        client = self._make_client()
        raw = make_europepmc_record(author_string="")
        result = client._normalise(raw)
        assert result["authors"] == []

    def test_single_author(self):
        client = self._make_client()
        raw = make_europepmc_record(author_string="Solo H")
        result = client._normalise(raw)
        assert result["authors"] == [{"name": "Solo H"}]

    def test_doi_none_when_missing(self):
        client = self._make_client()
        raw = make_europepmc_record(doi=None)
        result = client._normalise(raw)
        assert result["doi"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_europepmc.py::TestNormalise -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.ingest.europepmc'`

- [ ] **Step 3: Create Europe PMC client with normalisation**

Create `pipeline/ingest/europepmc.py`:

```python
"""Async client for the Europe PMC REST API.

Usage:
    async with EuropepmcClient() as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

log = structlog.get_logger()


class EuropepmcClient:
    """Async client for Europe PMC preprint search."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    PAGE_SIZE = 1000

    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> EuropepmcClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        raise NotImplementedError  # Implemented in Task 4

    # -- Internal ------------------------------------------------------------

    def _normalise(self, raw: dict) -> dict:
        """Map a Europe PMC record to the common metadata schema."""
        author_str = raw.get("authorString", "")
        authors_list = [{"name": a.strip()} for a in author_str.split(", ") if a.strip()]

        return {
            "doi": raw.get("doi"),
            "title": raw.get("title", "").strip(),
            "authors": authors_list,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": html.unescape(raw.get("abstractText", "")),
            "source_server": "europepmc",
            "posted_date": date.fromisoformat(raw["firstPublicationDate"]),
            "subject_category": None,
            "version": 1,
            "full_text_url": None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_europepmc.py::TestNormalise -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/ingest/europepmc.py tests/test_europepmc.py
uv run ruff format pipeline/ingest/europepmc.py tests/test_europepmc.py
git add pipeline/ingest/europepmc.py tests/test_europepmc.py
git commit -m "feat: add Europe PMC client with field normalisation"
```

---

### Task 4: Europe PMC client — fetch, pagination, and retry

**Files:**
- Modify: `pipeline/ingest/europepmc.py`
- Modify: `tests/test_europepmc.py`

- [ ] **Step 1: Write failing fetch and pagination tests**

Add to `tests/test_europepmc.py`:

```python
import httpx
import pytest
import respx

from tests.conftest import make_europepmc_record, make_europepmc_response


class TestFetch:
    """Tests for EuropepmcClient.fetch_papers — HTTP fetch + pagination."""

    SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    @respx.mock
    async def test_fetch_single_page(self):
        """Fetch results that fit in one page — no pagination needed."""
        records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}")
            for i in range(3)
        ]
        page1 = make_europepmc_response(records, hit_count=3, next_cursor="same_cursor")
        # Second call returns empty to stop iteration (cursor didn't change)
        page2 = make_europepmc_response([], hit_count=3, next_cursor="same_cursor")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 3
        assert papers[0]["doi"] == "10.1101/2026.03.01.0"
        assert papers[0]["source_server"] == "europepmc"

    @respx.mock
    async def test_fetch_cursor_pagination(self):
        """Fetch results across two pages using cursor-based pagination."""
        page1_records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}")
            for i in range(3)
        ]
        page2_records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}")
            for i in range(3, 5)
        ]
        page1 = make_europepmc_response(page1_records, hit_count=5, next_cursor="cursor_page2")
        page2 = make_europepmc_response(page2_records, hit_count=5, next_cursor="cursor_page2")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 5))]

        assert len(papers) == 5
        assert route.call_count == 2

    @respx.mock
    async def test_fetch_empty_result(self):
        """No papers found — yields nothing."""
        response = make_europepmc_response([], hit_count=0)
        respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(200, json=response))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0


class TestRetry:
    """Tests for EuropepmcClient retry and error handling."""

    SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert route.call_count >= 2

    @respx.mock
    async def test_503_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1

    @respx.mock
    async def test_timeout_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.TimeoutException("connect timeout"),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(429))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

    @respx.mock
    async def test_non_retryable_error_raises_immediately(self):
        route = respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(404))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            with pytest.raises(httpx.HTTPStatusError):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_europepmc.py::TestFetch tests/test_europepmc.py::TestRetry -v`
Expected: FAIL — `NotImplementedError` from `fetch_papers`

- [ ] **Step 3: Implement fetch_papers and _fetch_page**

Replace the `fetch_papers` stub and add `_fetch_page` in `pipeline/ingest/europepmc.py`:

```python
    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        cursor_mark = "*"
        while True:
            data = await self._fetch_page(from_date, to_date, cursor_mark)
            results = data.get("resultList", {}).get("result", [])
            if not results:
                break

            for raw in results:
                yield self._normalise(raw)

            next_cursor = data.get("nextCursorMark")
            if next_cursor is None or next_cursor == cursor_mark:
                break
            cursor_mark = next_cursor

            log.info(
                "page_fetched",
                source="europepmc",
                cursor=cursor_mark,
                hit_count=data.get("hitCount", 0),
                fetched_this_page=len(results),
            )

    async def _fetch_page(self, from_date: date, to_date: date, cursor_mark: str) -> dict:
        """Fetch a single page from the Europe PMC API with retry and backoff."""
        assert self._client is not None, "Use EuropepmcClient as async context manager"

        query = f"(FIRST_PDATE:[{from_date} TO {to_date}]) AND SRC:PPR"
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": self.PAGE_SIZE,
            "cursorMark": cursor_mark,
        }

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(self.BASE_URL, params=params, timeout=30.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="europepmc",
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
                    "timeout", source="europepmc", attempt=attempt, backoff=backoff
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Europe PMC failed after {self.max_retries} retries")
```

- [ ] **Step 4: Run all Europe PMC tests**

Run: `uv run pytest tests/test_europepmc.py -v`
Expected: All 14 tests PASS (6 normalisation + 3 fetch + 5 retry)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix pipeline/ingest/europepmc.py tests/test_europepmc.py
uv run ruff format pipeline/ingest/europepmc.py tests/test_europepmc.py
git add pipeline/ingest/europepmc.py tests/test_europepmc.py
git commit -m "feat: add Europe PMC fetch with cursor pagination and retry"
```

---

### Task 5: PubMed fixture data

**Files:**
- Create: `tests/fixtures/sample_pubmed.xml`

- [ ] **Step 1: Create sample PubMed fixture file**

Create `tests/fixtures/sample_pubmed.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000001</PMID>
      <Article>
        <ArticleTitle>Novel reverse genetics system for influenza A virus</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Influenza A viruses remain a major pandemic threat.</AbstractText>
          <AbstractText Label="METHODS">We developed a simplified eight-plasmid reverse genetics system.</AbstractText>
          <AbstractText Label="RESULTS">The system achieved 10-fold higher rescue efficiency than existing methods.</AbstractText>
          <AbstractText Label="CONCLUSIONS">This simplified system lowers technical barriers to influenza research.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Chen</LastName>
            <ForeName>Wei</ForeName>
            <AffiliationInfo>
              <Affiliation>Department of Virology, Peking University, Beijing, China</Affiliation>
            </AffiliationInfo>
          </Author>
          <Author>
            <LastName>Zhang</LastName>
            <ForeName>Li</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Influenza A virus</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName>Reverse Genetics</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2026</Year><Month>3</Month><Day>15</Day>
        </PubMedPubDate>
      </History>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1234/journal.ppat.1234567</ArticleId>
        <ArticleId IdType="pmc">PMC9876543</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>

  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000002</PMID>
      <Article>
        <ArticleTitle>Directed evolution of <i>Clostridium botulinum</i> neurotoxin variants</ArticleTitle>
        <Abstract>
          <AbstractText>We used directed evolution to generate botulinum neurotoxin variants with altered substrate specificity and enhanced catalytic activity.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Rodriguez</LastName>
            <ForeName>Maria Elena</ForeName>
            <AffiliationInfo>
              <Affiliation>Institute of Toxicology, Universidad de Buenos Aires</Affiliation>
            </AffiliationInfo>
          </Author>
          <Author>
            <LastName>Kim</LastName>
            <ForeName>Sung-Ho</ForeName>
          </Author>
          <Author>
            <LastName>O'Brien</LastName>
            <ForeName>Patrick</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Botulinum Toxins</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName>Directed Molecular Evolution</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2026</Year><Month>3</Month><Day>10</Day>
        </PubMedPubDate>
      </History>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1038/s41586-026-00001-1</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>

  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000003</PMID>
      <Article>
        <ArticleTitle>Epidemiological surveillance of seasonal influenza in Southeast Asia</ArticleTitle>
        <Abstract>
          <AbstractText>Routine surveillance of circulating influenza strains during the 2025-2026 season across seven Southeast Asian countries.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Nguyen</LastName>
            <ForeName>Thi</ForeName>
            <AffiliationInfo>
              <Affiliation>WHO Collaborating Centre, National Institute of Hygiene, Hanoi, Vietnam</Affiliation>
            </AffiliationInfo>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Influenza, Human</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName>Epidemiological Monitoring</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2026</Year><Month>3</Month><Day>12</Day>
        </PubMedPubDate>
      </History>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1016/j.ijid.2026.01.005</ArticleId>
        <ArticleId IdType="pmc">PMC9876544</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>

  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000004</PMID>
      <Article>
        <ArticleTitle>Metagenomic discovery of novel bat paramyxoviruses</ArticleTitle>
        <Abstract>
          <AbstractText>Deep sequencing of bat guano samples from caves in Yunnan Province revealed three novel paramyxoviruses with broad host range potential.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Li</LastName>
            <ForeName>Xiang</ForeName>
          </Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2026</Year><Month>3</Month><Day>20</Day>
        </PubMedPubDate>
      </History>
      <ArticleIdList>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>

  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000005</PMID>
      <Article>
        <ArticleTitle>CRISPR-Cas13 targeting of SARS-CoV-2 RNA in human airway cells</ArticleTitle>
        <Abstract>
          <AbstractText Label="OBJECTIVE">To evaluate CRISPR-Cas13 as a therapeutic against SARS-CoV-2.</AbstractText>
          <AbstractText Label="METHODS">We designed guide RNAs targeting conserved regions of the SARS-CoV-2 genome and delivered via lipid nanoparticles to human bronchial epithelial cells.</AbstractText>
          <AbstractText Label="RESULTS">Viral RNA was reduced by 99.7% at 48 hours post-treatment.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Patel</LastName>
            <ForeName>Sanjay</ForeName>
            <AffiliationInfo>
              <Affiliation>Broad Institute of MIT and Harvard, Cambridge, MA</Affiliation>
            </AffiliationInfo>
          </Author>
          <Author>
            <LastName>Wu</LastName>
            <ForeName>Feng</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>CRISPR-Cas Systems</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName>SARS-CoV-2</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2026</Year><Month>3</Month><Day>18</Day>
        </PubMedPubDate>
      </History>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1126/science.abm9999</ArticleId>
        <ArticleId IdType="pmc">PMC9876545</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
```

Note: Article 1 has a structured abstract (4 labels), DOI, PMC ID, and MeSH terms. Article 2 has inline `<i>` markup in the title, 3 authors, DOI but no PMC ID. Article 3 has a simple abstract, 1 author. Article 4 has no DOI and no MeSH terms (DOI-less edge case). Article 5 has a structured abstract with 3 labels and both DOI + PMC ID.

- [ ] **Step 2: Verify fixture file is valid XML**

Run: `python3 -c "from lxml import etree; etree.parse('tests/fixtures/sample_pubmed.xml'); print('Valid XML')"`
Expected: `Valid XML`

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/sample_pubmed.xml
git commit -m "feat: add PubMed sample XML fixture data"
```

---

### Task 6: PubMed client — XML parsing and normalisation

**Files:**
- Create: `pipeline/ingest/pubmed.py`
- Create: `tests/test_pubmed.py`

- [ ] **Step 1: Write failing XML parsing tests**

Create `tests/test_pubmed.py`:

```python
"""Tests for pipeline.ingest.pubmed — PubMed E-utilities client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx


# ---------------------------------------------------------------------------
# XML helpers — build PubmedArticle fragments for targeted testing
# ---------------------------------------------------------------------------

def _article_xml(
    pmid: str = "38000001",
    title: str = "Test Article",
    authors: list[tuple[str, str]] | None = None,
    affiliation: str | None = None,
    abstract_parts: list[tuple[str | None, str]] | None = None,
    doi: str | None = "10.1234/test.001",
    pmc_id: str | None = None,
    mesh_terms: list[str] | None = None,
    pub_year: str = "2026",
    pub_month: str = "3",
    pub_day: str = "15",
) -> str:
    """Build a single <PubmedArticle> XML string for testing."""
    if authors is None:
        authors = [("Smith", "John")]
    if abstract_parts is None:
        abstract_parts = [(None, "A test abstract.")]

    # Authors
    author_xml = ""
    for i, (last, fore) in enumerate(authors):
        affil_xml = ""
        if i == 0 and affiliation:
            affil_xml = f"<AffiliationInfo><Affiliation>{affiliation}</Affiliation></AffiliationInfo>"
        author_xml += f"<Author><LastName>{last}</LastName><ForeName>{fore}</ForeName>{affil_xml}</Author>"

    # Abstract
    abs_xml = ""
    for label, text in abstract_parts:
        if label:
            abs_xml += f'<AbstractText Label="{label}">{text}</AbstractText>'
        else:
            abs_xml += f"<AbstractText>{text}</AbstractText>"

    # Article IDs
    aid_xml = ""
    if doi:
        aid_xml += f'<ArticleId IdType="doi">{doi}</ArticleId>'
    if pmc_id:
        aid_xml += f'<ArticleId IdType="pmc">{pmc_id}</ArticleId>'

    # MeSH
    mesh_xml = ""
    if mesh_terms:
        mesh_xml = "<MeshHeadingList>"
        for term in mesh_terms:
            mesh_xml += f"<MeshHeading><DescriptorName>{term}</DescriptorName></MeshHeading>"
        mesh_xml += "</MeshHeadingList>"

    return f"""<PubmedArticle>
  <MedlineCitation>
    <PMID>{pmid}</PMID>
    <Article>
      <ArticleTitle>{title}</ArticleTitle>
      <Abstract>{abs_xml}</Abstract>
      <AuthorList>{author_xml}</AuthorList>
    </Article>
    {mesh_xml}
  </MedlineCitation>
  <PubmedData>
    <History>
      <PubMedPubDate PubStatus="pubmed">
        <Year>{pub_year}</Year><Month>{pub_month}</Month><Day>{pub_day}</Day>
      </PubMedPubDate>
    </History>
    <ArticleIdList>{aid_xml}</ArticleIdList>
  </PubmedData>
</PubmedArticle>"""


def _wrap_articles(*articles: str) -> bytes:
    """Wrap PubmedArticle XML strings in a PubmedArticleSet."""
    inner = "\n".join(articles)
    return f'<?xml version="1.0"?>\n<PubmedArticleSet>{inner}</PubmedArticleSet>'.encode()


class TestXmlParsing:
    """Tests for PubmedClient._parse_articles XML extraction."""

    def _make_client(self):
        from pipeline.ingest.pubmed import PubmedClient

        return PubmedClient(request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(
                title="Novel Virus Study",
                authors=[("Chen", "Wei"), ("Zhang", "Li")],
                affiliation="Peking University",
                doi="10.1234/test.001",
                pmc_id="PMC9876543",
                mesh_terms=["Virology", "Reverse Genetics"],
                pub_year="2026", pub_month="3", pub_day="15",
            )
        )
        articles = client._parse_articles(xml)

        assert len(articles) == 1
        a = articles[0]
        assert a["title"] == "Novel Virus Study"
        assert a["authors"] == [{"name": "Chen, W."}, {"name": "Zhang, L."}]
        assert a["corresponding_institution"] == "Peking University"
        assert a["doi"] == "10.1234/test.001"
        assert a["posted_date"] == date(2026, 3, 15)
        assert a["source_server"] == "pubmed"
        assert a["subject_category"] == "Virology; Reverse Genetics"
        assert a["full_text_url"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9876543/"
        assert a["version"] == 1

    def test_author_formatting(self):
        """Authors formatted as 'Surname, I.' to match bioRxiv convention."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(authors=[
                ("Rodriguez", "Maria Elena"),
                ("O'Brien", "Patrick"),
                ("Li", "X"),
            ])
        )
        articles = client._parse_articles(xml)
        assert articles[0]["authors"] == [
            {"name": "Rodriguez, M."},
            {"name": "O'Brien, P."},
            {"name": "Li, X."},
        ]

    def test_structured_abstract(self):
        """Multiple AbstractText elements with labels are concatenated."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(abstract_parts=[
                ("BACKGROUND", "Viruses are bad."),
                ("METHODS", "We did science."),
                ("RESULTS", "It worked."),
                ("CONCLUSIONS", "Good news."),
            ])
        )
        articles = client._parse_articles(xml)
        abstract = articles[0]["abstract"]
        assert "BACKGROUND: Viruses are bad." in abstract
        assert "METHODS: We did science." in abstract
        assert "RESULTS: It worked." in abstract
        assert "CONCLUSIONS: Good news." in abstract

    def test_simple_abstract(self):
        """Single AbstractText without label."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(abstract_parts=[(None, "A plain abstract.")])
        )
        articles = client._parse_articles(xml)
        assert articles[0]["abstract"] == "A plain abstract."

    def test_doi_less_article(self):
        """Article without DOI — doi field should be None."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(doi=None, pmc_id=None)
        )
        articles = client._parse_articles(xml)
        assert articles[0]["doi"] is None
        assert articles[0]["full_text_url"] is None

    def test_pmc_full_text_url(self):
        """Article with PMC ID gets a full-text URL."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(pmc_id="PMC1234567")
        )
        articles = client._parse_articles(xml)
        assert articles[0]["full_text_url"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/"

    def test_no_pmc_id_no_url(self):
        """Article without PMC ID — full_text_url is None."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(doi="10.1234/test", pmc_id=None)
        )
        articles = client._parse_articles(xml)
        assert articles[0]["full_text_url"] is None

    def test_inline_markup_in_title(self):
        """Inline XML markup (<i>, <sub>) in title is stripped, text preserved."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(title="Directed evolution of <i>Clostridium botulinum</i> neurotoxin")
        )
        articles = client._parse_articles(xml)
        assert articles[0]["title"] == "Directed evolution of Clostridium botulinum neurotoxin"

    def test_no_mesh_terms(self):
        """Article without MeSH headings — subject_category is None."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(mesh_terms=None)
        )
        articles = client._parse_articles(xml)
        assert articles[0]["subject_category"] is None

    def test_multiple_articles(self):
        """Multiple articles in one PubmedArticleSet are all parsed."""
        client = self._make_client()
        xml = _wrap_articles(
            _article_xml(pmid="1", title="Paper A", doi="10.1/a"),
            _article_xml(pmid="2", title="Paper B", doi="10.1/b"),
            _article_xml(pmid="3", title="Paper C", doi="10.1/c"),
        )
        articles = client._parse_articles(xml)
        assert len(articles) == 3
        assert [a["title"] for a in articles] == ["Paper A", "Paper B", "Paper C"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pubmed.py::TestXmlParsing -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.ingest.pubmed'`

- [ ] **Step 3: Create PubMed client with XML parsing**

Create `pipeline/ingest/pubmed.py`:

```python
"""Async client for PubMed E-utilities (esearch + efetch).

Usage:
    async with PubmedClient(api_key="...", query_mode="all") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog
from lxml import etree

log = structlog.get_logger()

DEFAULT_MESH_QUERY = (
    '(virology[MeSH] OR microbiology[MeSH] OR "synthetic biology"[MeSH] OR '
    '"genetic engineering"[MeSH] OR "gain of function"[tiab] OR '
    '"gain-of-function"[tiab] OR "directed evolution"[tiab] OR '
    '"reverse genetics"[tiab] OR "gene drive"[tiab] OR "gene drives"[tiab] OR '
    '"select agent"[tiab] OR "select agents"[tiab] OR '
    '"dual use"[tiab] OR "dual-use"[tiab] OR '
    '"pathogen enhancement"[tiab] OR "immune evasion"[tiab] OR '
    '"host range"[tiab] OR "transmissibility"[tiab] OR '
    '"virulence factor"[tiab] OR "virulence factors"[tiab] OR '
    'toxins[MeSH] OR "biological warfare"[MeSH] OR "biodefense"[MeSH] OR '
    'CRISPR[tiab] OR "base editing"[tiab] OR '
    '"pandemic preparedness"[tiab] OR "pandemic pathogen"[tiab] OR '
    '"biosafety level"[tiab] OR "BSL-3"[tiab] OR "BSL-4"[tiab] OR '
    'prions[MeSH] OR "mirror life"[tiab] OR "xenobiology"[tiab] OR '
    '"de novo protein design"[tiab] OR "protein design"[tiab] OR '
    '"aerosol transmission"[tiab] OR "airborne transmission"[tiab])'
)


class PubmedClient:
    """Async client for PubMed via NCBI E-utilities."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    FETCH_BATCH_SIZE = 200

    def __init__(
        self,
        api_key: str = "",
        request_delay: float = 0.1,
        max_retries: int = 3,
        query_mode: str = "all",
        mesh_query: str = DEFAULT_MESH_QUERY,
    ) -> None:
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.query_mode = query_mode
        self.mesh_query = mesh_query
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PubmedClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Search PubMed and yield normalised paper dicts."""
        raise NotImplementedError  # Implemented in Task 7

    # -- XML parsing ---------------------------------------------------------

    def _parse_articles(self, xml_bytes: bytes) -> list[dict]:
        """Parse PubmedArticleSet XML into normalised dicts."""
        root = etree.fromstring(xml_bytes)
        articles = []
        for elem in root.findall(".//PubmedArticle"):
            try:
                articles.append(self._normalise_article(elem))
            except Exception:
                log.exception("pubmed_parse_error")
                continue
        return articles

    def _normalise_article(self, elem) -> dict:
        """Extract fields from a single PubmedArticle element."""
        citation = elem.find("MedlineCitation")
        article = citation.find("Article")

        # Title — extract text only, strip inline XML markup like <i>, <sub>
        title_elem = article.find("ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

        # Authors
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            if last:
                initial = f"{fore[0]}." if fore else ""
                name = f"{last}, {initial}" if initial else last
                authors.append({"name": name})

        # Corresponding institution (first author's affiliation)
        first_affil = article.findtext(".//Author[1]/AffiliationInfo/Affiliation")

        # Abstract (may be structured with labels)
        abstract_parts = []
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label")
            text = "".join(abs_text.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Article IDs — DOI and PMC from PubmedData
        doi = None
        pmc_id = None
        pubmed_data = elem.find("PubmedData")
        if pubmed_data is not None:
            for aid in pubmed_data.findall(".//ArticleId"):
                id_type = aid.get("IdType")
                if id_type == "doi" and doi is None:
                    doi = aid.text
                elif id_type == "pmc" and pmc_id is None:
                    pmc_id = aid.text

        # Publication date
        posted_date = self._extract_date(elem)

        # MeSH terms
        mesh_terms = [
            desc.text
            for desc in citation.findall(".//MeshHeading/DescriptorName")
            if desc.text
        ]
        subject_category = "; ".join(mesh_terms) if mesh_terms else None

        # Full text URL from PMC
        full_text_url = (
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
            if pmc_id
            else None
        )

        return {
            "doi": doi,
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": first_affil,
            "abstract": abstract,
            "source_server": "pubmed",
            "posted_date": posted_date,
            "subject_category": subject_category,
            "version": 1,
            "full_text_url": full_text_url,
        }

    def _extract_date(self, elem) -> date:
        """Extract publication date from PubmedArticle."""
        for pub_date in elem.findall(".//PubmedData/History/PubMedPubDate"):
            if pub_date.get("PubStatus") == "pubmed":
                year = int(pub_date.findtext("Year", "0"))
                month = int(pub_date.findtext("Month", "1"))
                day = int(pub_date.findtext("Day", "1"))
                return date(year, month, day)
        return date.today()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pubmed.py::TestXmlParsing -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/ingest/pubmed.py tests/test_pubmed.py
uv run ruff format pipeline/ingest/pubmed.py tests/test_pubmed.py
git add pipeline/ingest/pubmed.py tests/test_pubmed.py
git commit -m "feat: add PubMed client with XML parsing and normalisation"
```

---

### Task 7: PubMed client — search, fetch, query modes, and retry

**Files:**
- Modify: `pipeline/ingest/pubmed.py`
- Modify: `tests/test_pubmed.py`

- [ ] **Step 1: Write failing search and fetch tests**

Add to `tests/test_pubmed.py`:

```python
def _esearch_response(count: int = 5, webenv: str = "WEBENV_123", query_key: str = "1") -> dict:
    """Build an esearch JSON response."""
    return {
        "esearchresult": {
            "count": str(count),
            "webenv": webenv,
            "querykey": query_key,
            "idlist": [],
        }
    }


class TestSearch:
    """Tests for PubmedClient._search — esearch query construction."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    @respx.mock
    async def test_search_parses_response(self):
        """esearch returns webenv, query_key, count."""
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=42))
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            webenv, query_key, count = await client._search(
                date(2026, 3, 1), date(2026, 3, 1)
            )

        assert webenv == "WEBENV_123"
        assert query_key == "1"
        assert count == 42

    @respx.mock
    async def test_query_mode_all_no_term(self):
        """In 'all' mode, no term parameter is sent."""
        route = respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response())
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0, query_mode="all") as client:
            await client._search(date(2026, 3, 1), date(2026, 3, 1))

        request = route.calls[0].request
        assert "term" not in str(request.url)

    @respx.mock
    async def test_query_mode_mesh_filtered_includes_term(self):
        """In 'mesh_filtered' mode, the MeSH query is included as term."""
        route = respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response())
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(
            request_delay=0, query_mode="mesh_filtered"
        ) as client:
            await client._search(date(2026, 3, 1), date(2026, 3, 1))

        request = route.calls[0].request
        assert "virology" in str(request.url)

    @respx.mock
    async def test_api_key_included_when_set(self):
        """NCBI API key is passed as query parameter when configured."""
        route = respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response())
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(
            request_delay=0, api_key="test_ncbi_key"
        ) as client:
            await client._search(date(2026, 3, 1), date(2026, 3, 1))

        request = route.calls[0].request
        assert "test_ncbi_key" in str(request.url)

    @respx.mock
    async def test_date_format(self):
        """Dates are formatted as YYYY/MM/DD for PubMed."""
        route = respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response())
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            await client._search(date(2026, 3, 1), date(2026, 3, 15))

        request = route.calls[0].request
        url_str = str(request.url)
        assert "2026%2F03%2F01" in url_str or "2026/03/01" in url_str
        assert "2026%2F03%2F15" in url_str or "2026/03/15" in url_str


class TestFetch:
    """Tests for PubmedClient.fetch_papers — full esearch+efetch pipeline."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    @respx.mock
    async def test_fetch_single_batch(self):
        """Fetch <200 results — single efetch call."""
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=2))
        )
        xml = _wrap_articles(
            _article_xml(pmid="1", title="Paper A", doi="10.1/a"),
            _article_xml(pmid="2", title="Paper B", doi="10.1/b"),
        )
        respx.get(self.EFETCH_URL).mock(
            return_value=httpx.Response(200, content=xml)
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 2
        assert papers[0]["title"] == "Paper A"
        assert papers[1]["title"] == "Paper B"

    @respx.mock
    async def test_fetch_multiple_batches(self):
        """Fetch >200 results — multiple efetch calls paginating via retstart."""
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=3))
        )

        # Mock two efetch calls (batch_size=2 for test, overridden below)
        batch1 = _wrap_articles(
            _article_xml(pmid="1", title="Paper A"),
            _article_xml(pmid="2", title="Paper B"),
        )
        batch2 = _wrap_articles(
            _article_xml(pmid="3", title="Paper C"),
        )
        efetch_route = respx.get(self.EFETCH_URL).mock(
            side_effect=[
                httpx.Response(200, content=batch1),
                httpx.Response(200, content=batch2),
            ]
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            client.FETCH_BATCH_SIZE = 2  # Override for test
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 3
        assert efetch_route.call_count == 2

    @respx.mock
    async def test_fetch_zero_results(self):
        """esearch returns count=0 — yields nothing, no efetch call."""
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=0))
        )
        efetch_route = respx.get(self.EFETCH_URL).mock(
            return_value=httpx.Response(200, content=b"<PubmedArticleSet/>")
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 0
        assert efetch_route.call_count == 0


class TestRetry:
    """Tests for PubmedClient retry and error handling."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    @respx.mock
    async def test_esearch_429_retries(self):
        route = respx.get(self.ESEARCH_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_esearch_response(count=0)),
            ]
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 0
        assert route.call_count == 2

    @respx.mock
    async def test_efetch_503_retries(self):
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=1))
        )
        xml = _wrap_articles(_article_xml(title="Recovered"))
        efetch_route = respx.get(self.EFETCH_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, content=xml),
            ]
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert papers[0]["title"] == "Recovered"
        assert efetch_route.call_count == 2

    @respx.mock
    async def test_timeout_retries(self):
        respx.get(self.ESEARCH_URL).mock(
            return_value=httpx.Response(200, json=_esearch_response(count=1))
        )
        xml = _wrap_articles(_article_xml(title="After Timeout"))
        respx.get(self.EFETCH_URL).mock(
            side_effect=[
                httpx.TimeoutException("read timeout"),
                httpx.Response(200, content=xml),
            ]
        )

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get(self.ESEARCH_URL).mock(return_value=httpx.Response(429))

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

    @respx.mock
    async def test_non_retryable_error_raises_immediately(self):
        route = respx.get(self.ESEARCH_URL).mock(return_value=httpx.Response(400))

        from pipeline.ingest.pubmed import PubmedClient

        async with PubmedClient(request_delay=0) as client:
            with pytest.raises(httpx.HTTPStatusError):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pubmed.py::TestSearch tests/test_pubmed.py::TestFetch tests/test_pubmed.py::TestRetry -v`
Expected: FAIL — `NotImplementedError` from `fetch_papers` and `_search`

- [ ] **Step 3: Implement search, fetch, and retry methods**

Replace the `fetch_papers` stub and add `_search`, `_fetch_batch`, `_request_json`, and `_request_xml` methods in `pipeline/ingest/pubmed.py`:

```python
    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Search PubMed and yield normalised paper dicts."""
        webenv, query_key, count = await self._search(from_date, to_date)
        if count == 0:
            return

        log.info("pubmed_search_complete", count=count, query_mode=self.query_mode)

        for retstart in range(0, count, self.FETCH_BATCH_SIZE):
            articles = await self._fetch_batch(webenv, query_key, retstart)
            for article in articles:
                yield article

            if retstart + self.FETCH_BATCH_SIZE < count:
                log.info(
                    "pubmed_batch_fetched",
                    retstart=retstart,
                    batch_size=len(articles),
                    total=count,
                )

    # -- HTTP helpers --------------------------------------------------------

    async def _search(self, from_date: date, to_date: date) -> tuple[str, str, int]:
        """Run esearch and return (webenv, query_key, count)."""
        params: dict = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": 0,
            "usehistory": "y",
            "datetype": "pdat",
            "mindate": from_date.strftime("%Y/%m/%d"),
            "maxdate": to_date.strftime("%Y/%m/%d"),
        }
        if self.query_mode == "mesh_filtered":
            params["term"] = self.mesh_query
        if self.api_key:
            params["api_key"] = self.api_key

        data = await self._request_json(self.ESEARCH_URL, params)
        result = data.get("esearchresult", {})
        return (
            result.get("webenv", ""),
            result.get("querykey", ""),
            int(result.get("count", 0)),
        )

    async def _fetch_batch(
        self, webenv: str, query_key: str, retstart: int
    ) -> list[dict]:
        """Fetch a batch of articles via efetch and parse XML."""
        params: dict = {
            "db": "pubmed",
            "rettype": "xml",
            "retmode": "xml",
            "retmax": self.FETCH_BATCH_SIZE,
            "retstart": retstart,
            "webenv": webenv,
            "query_key": query_key,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        xml_bytes = await self._request_xml(self.EFETCH_URL, params)
        return self._parse_articles(xml_bytes)

    async def _request_json(self, url: str, params: dict) -> dict:
        """Make a request expecting JSON, with retry and backoff."""
        assert self._client is not None, "Use PubmedClient as async context manager"

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="pubmed",
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
                    "timeout", source="pubmed", attempt=attempt, backoff=backoff
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"PubMed failed after {self.max_retries} retries: {url}")

    async def _request_xml(self, url: str, params: dict) -> bytes:
        """Make a request expecting XML, with retry and backoff."""
        assert self._client is not None, "Use PubmedClient as async context manager"

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="pubmed",
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
                    "timeout", source="pubmed", attempt=attempt, backoff=backoff
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"PubMed failed after {self.max_retries} retries: {url}")
```

- [ ] **Step 4: Run all PubMed tests**

Run: `uv run pytest tests/test_pubmed.py -v`
Expected: All tests PASS (10 XML parsing + 5 search + 3 fetch + 5 retry = 23)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (existing + Europe PMC + PubMed)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix pipeline/ingest/pubmed.py tests/test_pubmed.py
uv run ruff format pipeline/ingest/pubmed.py tests/test_pubmed.py
git add pipeline/ingest/pubmed.py tests/test_pubmed.py
git commit -m "feat: add PubMed search, fetch, query modes, and retry"
```

---

### Task 8: Final integration verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS. Expected test counts:
- `test_config.py`: 4 tests
- `test_models.py`: 4 tests
- `test_db.py`: existing tests
- `test_ingest.py`: existing bioRxiv tests
- `test_dedup.py`: existing dedup tests
- `test_europepmc.py`: ~14 tests
- `test_pubmed.py`: ~23 tests

- [ ] **Step 2: Run lint and format checks**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors, no formatting changes needed

- [ ] **Step 3: Verify imports are clean**

Run: `python -c "from pipeline.ingest.europepmc import EuropepmcClient; from pipeline.ingest.pubmed import PubmedClient; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Tag the milestone**

```bash
git tag -f phase2-sp1-complete
```