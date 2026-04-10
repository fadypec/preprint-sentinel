# Batch 4: Tier 2 Ingest Clients, Medium-Severity Fixes, Backup Scripts, Frontend Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add arXiv, Crossref-based (Research Square, ChemRxiv, SSRN), and Zenodo ingest clients; fix remaining medium-severity audit issues; add database backup/restore scripts; bootstrap frontend test framework.

**Architecture:** Each new ingest client follows the existing async context manager pattern (see `biorxiv.py`), uses the shared `request_with_retry()` helper, yields normalized dicts matching the common schema, and registers in the orchestrator's `_run_ingest()` source list. Medium fixes are surgical edits. Backup scripts wrap `pg_dump`/`pg_restore`. Frontend tests use Vitest + React Testing Library.

**Tech Stack:** Python 3.11+, httpx, lxml (for arXiv Atom XML), structlog, respx (tests), Vitest, @testing-library/react, happy-dom

---

### Task 1: arXiv Ingest Client

**Files:**
- Create: `pipeline/ingest/arxiv.py`
- Create: `tests/test_arxiv.py`
- Create: `tests/fixtures/sample_arxiv_atom.xml`

The arXiv API at `https://export.arxiv.org/api/query` returns Atom XML. We filter on `q-bio.*` categories and `submittedDate` ranges. arXiv recommends >= 3s delay between requests.

- [ ] **Step 1: Create the Atom XML fixture**

Save a representative arXiv Atom response to `tests/fixtures/sample_arxiv_atom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query: cat:q-bio*</title>
  <id>http://arxiv.org/api/query</id>
  <opensearch:totalResults>2</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>100</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2026.12345v1</id>
    <title>Novel CRISPR-Based Gene Drive in Anopheles Mosquitoes</title>
    <summary>We describe a self-propagating gene drive system targeting malaria vectors using a dual-gRNA CRISPR construct.</summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <published>2026-03-15T00:00:00Z</published>
    <updated>2026-03-15T12:00:00Z</updated>
    <link href="http://arxiv.org/abs/2026.12345v1" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2026.12345v1" rel="related" type="application/pdf" title="pdf"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="q-bio.GN"/>
    <category term="q-bio.GN"/>
    <category term="q-bio.PE"/>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1234/example.2026</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2026.67890v2</id>
    <title>Protein Design via Diffusion Models for Therapeutic Enzymes</title>
    <summary>We present a diffusion-based approach to de novo protein design optimised for catalytic activity.</summary>
    <author><name>Carol Zhang</name></author>
    <published>2026-03-16T00:00:00Z</published>
    <updated>2026-03-17T09:00:00Z</updated>
    <link href="http://arxiv.org/abs/2026.67890v2" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2026.67890v2" rel="related" type="application/pdf" title="pdf"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="q-bio.BM"/>
    <category term="q-bio.BM"/>
    <category term="cs.AI"/>
  </entry>
</feed>
```

- [ ] **Step 2: Write normalisation tests**

Create `tests/test_arxiv.py`:

```python
"""Tests for pipeline.ingest.arxiv — arXiv Atom API client."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_arxiv_atom.xml"


def _make_client():
    from pipeline.ingest.arxiv import ArxivClient
    return ArxivClient(request_delay=0)


class TestParseAtom:
    """Tests for ArxivClient._parse_atom XML parsing."""

    def test_parses_two_entries(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        assert len(entries) == 2

    def test_total_results_extracted(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        # First entry fields
        assert entries[0]["title"] == "Novel CRISPR-Based Gene Drive in Anopheles Mosquitoes"
        assert entries[0]["authors"] == ["Alice Smith", "Bob Jones"]
        assert entries[0]["doi"] == "10.1234/example.2026"
        assert entries[0]["primary_category"] == "q-bio.GN"
        assert entries[0]["pdf_url"] == "http://arxiv.org/pdf/2026.12345v1"

    def test_entry_without_doi(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        # Second entry has no doi element
        assert entries[1]["doi"] is None
        assert entries[1]["primary_category"] == "q-bio.BM"


class TestNormalise:
    """Tests for ArxivClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        entry = {
            "title": "  Test Title  ",
            "summary": "Abstract text here.",
            "authors": ["Alice Smith", "Bob Jones"],
            "published": "2026-03-15T00:00:00Z",
            "doi": "10.1234/example",
            "primary_category": "q-bio.GN",
            "pdf_url": "http://arxiv.org/pdf/2026.12345v1",
            "arxiv_id": "2026.12345v1",
        }
        result = client._normalise(entry)

        assert result["title"] == "Test Title"
        assert result["abstract"] == "Abstract text here."
        assert result["authors"] == [{"name": "Alice Smith"}, {"name": "Bob Jones"}]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["doi"] == "10.1234/example"
        assert result["source_server"] == "arxiv"
        assert result["subject_category"] == "q-bio.GN"
        assert result["full_text_url"] == "http://arxiv.org/pdf/2026.12345v1"
        assert result["version"] == 1

    def test_no_doi_gives_none(self):
        client = _make_client()
        entry = {
            "title": "Title",
            "summary": "Abstract",
            "authors": ["Author"],
            "published": "2026-03-15T00:00:00Z",
            "doi": None,
            "primary_category": "q-bio.BM",
            "pdf_url": None,
            "arxiv_id": "2026.67890v2",
        }
        result = client._normalise(entry)
        assert result["doi"] is None
        assert result["full_text_url"] is None

    def test_version_extracted_from_arxiv_id(self):
        client = _make_client()
        entry = {
            "title": "Title",
            "summary": "Abstract",
            "authors": ["Author"],
            "published": "2026-03-15T00:00:00Z",
            "doi": None,
            "primary_category": "q-bio.BM",
            "pdf_url": None,
            "arxiv_id": "2026.67890v3",
        }
        result = client._normalise(entry)
        assert result["version"] == 3


class TestFetch:
    """Tests for ArxivClient.fetch_papers — HTTP fetch + pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        xml_text = FIXTURE_PATH.read_text()
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=xml_text)
        )

        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]

        assert len(papers) == 2
        assert papers[0]["source_server"] == "arxiv"
        assert papers[0]["title"] == "Novel CRISPR-Based Gene Drive in Anopheles Mosquitoes"

    @respx.mock
    async def test_fetch_empty_result(self):
        empty_feed = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"'
            '      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
            '<opensearch:totalResults>0</opensearch:totalResults>'
            '</feed>'
        )
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=empty_feed)
        )

        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0


class TestRetry:
    """Tests for ArxivClient retry and error handling."""

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        xml_text = FIXTURE_PATH.read_text()
        url = "https://export.arxiv.org/api/query"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, text=xml_text),
            ]
        )
        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]
        assert len(papers) == 2
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(429)
        )
        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_arxiv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ingest.arxiv'`

- [ ] **Step 4: Implement the arXiv client**

Create `pipeline/ingest/arxiv.py`:

```python
"""Async client for the arXiv API (Atom feed).

Usage:
    async with ArxivClient() as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog
from lxml import etree

from pipeline.http_retry import request_with_retry
from pipeline.models import SourceServer

log = structlog.get_logger()

# Atom/arXiv XML namespaces
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivClient:
    """Async client for arXiv preprint search (q-bio categories)."""

    BASE_URL = "https://export.arxiv.org/api/query"
    PAGE_SIZE = 100
    CATEGORIES = ["q-bio"]

    def __init__(
        self,
        request_delay: float = 3.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ArxivClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts from arXiv q-bio categories."""
        for category in self.CATEGORIES:
            async for paper in self._fetch_category(category, from_date, to_date):
                yield paper

    # -- Internal ------------------------------------------------------------

    async def _fetch_category(
        self, category: str, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Paginate through all results for a single category."""
        start = 0
        while True:
            xml_text = await self._fetch_page(category, from_date, to_date, start)
            entries = self._parse_atom(xml_text)
            if not entries:
                break

            for entry in entries:
                yield self._normalise(entry)

            if len(entries) < self.PAGE_SIZE:
                break
            start += self.PAGE_SIZE

            log.info(
                "page_fetched",
                source="arxiv",
                category=category,
                start=start,
                fetched_this_page=len(entries),
            )

    async def _fetch_page(
        self, category: str, from_date: date, to_date: date, start: int
    ) -> str:
        """Fetch a single page from the arXiv API with retry."""
        if self._client is None:
            raise RuntimeError("Use ArxivClient as async context manager")

        date_from = from_date.strftime("%Y%m%d") + "0000"
        date_to = to_date.strftime("%Y%m%d") + "2359"
        query = f"cat:{category}* AND submittedDate:[{date_from} TO {date_to}]"

        params = {
            "search_query": query,
            "start": start,
            "max_results": self.PAGE_SIZE,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        resp = await request_with_retry(
            self._client,
            self.BASE_URL,
            params=params,
            timeout=60.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source="arxiv",
        )
        if resp is None:
            raise RuntimeError("arXiv returned unexpected None response")
        return resp.text

    def _parse_atom(self, xml_text: str) -> list[dict]:
        """Parse an Atom XML response into a list of entry dicts."""
        root = etree.fromstring(xml_text.encode("utf-8"))

        total = root.findtext("opensearch:totalResults", default="0", namespaces=_NS)
        if int(total) == 0:
            return []

        entries = []
        for entry_el in root.findall("atom:entry", _NS):
            arxiv_id_url = entry_el.findtext("atom:id", default="", namespaces=_NS)
            arxiv_id = arxiv_id_url.rsplit("/", 1)[-1] if arxiv_id_url else ""

            title = entry_el.findtext("atom:title", default="", namespaces=_NS)
            # arXiv titles often contain newlines — normalise whitespace
            title = re.sub(r"\s+", " ", title).strip()

            summary = entry_el.findtext("atom:summary", default="", namespaces=_NS)
            summary = re.sub(r"\s+", " ", summary).strip()

            authors = [
                el.findtext("atom:name", default="", namespaces=_NS)
                for el in entry_el.findall("atom:author", _NS)
            ]
            authors = [a for a in authors if a]

            published = entry_el.findtext("atom:published", default="", namespaces=_NS)

            # DOI (optional)
            doi = entry_el.findtext("arxiv:doi", default=None, namespaces=_NS)

            # Primary category
            primary_cat_el = entry_el.find("arxiv:primary_category", _NS)
            primary_category = (
                primary_cat_el.get("term") if primary_cat_el is not None else None
            )

            # PDF link
            pdf_url = None
            for link_el in entry_el.findall("atom:link", _NS):
                if link_el.get("title") == "pdf":
                    pdf_url = link_el.get("href")

            entries.append({
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "published": published,
                "doi": doi,
                "primary_category": primary_category,
                "pdf_url": pdf_url,
            })

        return entries

    def _normalise(self, entry: dict) -> dict:
        """Map a parsed Atom entry to the common metadata schema."""
        published_str = entry.get("published", "")
        posted_date = date.fromisoformat(published_str[:10]) if published_str else date.today()

        arxiv_id = entry.get("arxiv_id", "")
        version = 1
        version_match = re.search(r"v(\d+)$", arxiv_id)
        if version_match:
            version = int(version_match.group(1))

        return {
            "doi": entry.get("doi"),
            "title": entry.get("title", "").strip(),
            "authors": [{"name": a} for a in entry.get("authors", [])],
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": entry.get("summary", "").strip(),
            "source_server": SourceServer.ARXIV,
            "posted_date": posted_date,
            "subject_category": entry.get("primary_category"),
            "version": version,
            "full_text_url": entry.get("pdf_url"),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_arxiv.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/ingest/arxiv.py tests/test_arxiv.py tests/fixtures/sample_arxiv_atom.xml
git commit -m "feat: add arXiv ingest client for q-bio categories"
```

---

### Task 2: Crossref Ingest Client (Research Square, ChemRxiv, SSRN)

**Files:**
- Create: `pipeline/ingest/crossref.py`
- Create: `tests/test_crossref.py`

A single client harvests preprints from three servers via Crossref's `posted-content` type filter and DOI prefix filtering. Crossref uses cursor-based pagination.

DOI prefixes: Research Square = `10.21203`, ChemRxiv = `10.26434`, SSRN = `10.2139`.

- [ ] **Step 1: Write tests**

Create `tests/test_crossref.py`:

```python
"""Tests for pipeline.ingest.crossref — Crossref API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx


def _make_client(**kwargs):
    from pipeline.ingest.crossref import CrossrefClient
    return CrossrefClient(request_delay=0, **kwargs)


def _make_crossref_item(
    doi: str = "10.21203/rs.3.rs-1234567/v1",
    title: str = "Test Paper",
    given: str = "Alice",
    family: str = "Smith",
    abstract: str = "<p>Test abstract.</p>",
    posted_parts: list | None = None,
    subtype: str = "preprint",
) -> dict:
    """Create a Crossref work item matching the real API format."""
    if posted_parts is None:
        posted_parts = [[2026, 3, 15]]
    item: dict = {
        "DOI": doi,
        "title": [title],
        "author": [{"given": given, "family": family}],
        "abstract": abstract,
        "posted": {"date-parts": posted_parts},
        "subtype": subtype,
    }
    return item


def _make_crossref_response(
    items: list[dict],
    total: int | None = None,
    next_cursor: str | None = None,
) -> dict:
    """Wrap items in the Crossref API response envelope."""
    msg: dict = {
        "total-results": total if total is not None else len(items),
        "items": items,
    }
    if next_cursor:
        msg["next-cursor"] = next_cursor
    return {"status": "ok", "message-type": "work-list", "message": msg}


class TestNormalise:
    """Tests for CrossrefClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        item = _make_crossref_item(
            doi="10.21203/rs.3.rs-1234567/v1",
            title="  Research Square Paper  ",
            given="Alice",
            family="Smith",
            abstract="<p>An abstract with <b>HTML</b> tags.</p>",
            posted_parts=[[2026, 3, 15]],
        )
        result = client._normalise(item, "research_square")

        assert result["doi"] == "10.21203/rs.3.rs-1234567/v1"
        assert result["title"] == "Research Square Paper"
        assert result["authors"] == [{"name": "Smith, Alice"}]
        assert result["abstract"] == "An abstract with HTML tags."
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "research_square"
        assert result["version"] == 1

    def test_chemrxiv_source_server(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.26434/chemrxiv-2026-abc")
        result = client._normalise(item, "chemrxiv")
        assert result["source_server"] == "chemrxiv"

    def test_ssrn_source_server(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.2139/ssrn.4000001")
        result = client._normalise(item, "ssrn")
        assert result["source_server"] == "ssrn"

    def test_multiple_authors(self):
        client = _make_client()
        item = _make_crossref_item()
        item["author"] = [
            {"given": "Alice", "family": "Smith"},
            {"given": "Bob", "family": "Jones"},
            {"family": "Consortium"},  # no given name
        ]
        result = client._normalise(item, "research_square")
        assert result["authors"] == [
            {"name": "Smith, Alice"},
            {"name": "Jones, Bob"},
            {"name": "Consortium"},
        ]

    def test_missing_abstract(self):
        client = _make_client()
        item = _make_crossref_item()
        del item["abstract"]
        result = client._normalise(item, "research_square")
        assert result["abstract"] == ""

    def test_version_from_doi(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.21203/rs.3.rs-1234567/v3")
        result = client._normalise(item, "research_square")
        assert result["version"] == 3

    def test_partial_date_month_only(self):
        client = _make_client()
        item = _make_crossref_item(posted_parts=[[2026, 3]])
        result = client._normalise(item, "research_square")
        assert result["posted_date"] == date(2026, 3, 1)


class TestFetch:
    """Tests for CrossrefClient.fetch_papers — HTTP pagination."""

    @respx.mock
    async def test_fetch_single_source_single_page(self):
        items = [_make_crossref_item(doi=f"10.21203/rs.3.rs-{i}/v1") for i in range(3)]
        response = _make_crossref_response(items, total=3)

        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        # Only fetch research_square to simplify test
        async with CrossrefClient(request_delay=0, sources={"research_square": "10.21203"}) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 3
        assert all(p["source_server"] == "research_square" for p in papers)

    @respx.mock
    async def test_fetch_empty_result(self):
        response = _make_crossref_response([], total=0)
        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(request_delay=0, sources={"research_square": "10.21203"}) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_html_stripped_from_abstract(self):
        item = _make_crossref_item(abstract="<jats:p>Clean <jats:italic>abstract</jats:italic>.</jats:p>")
        response = _make_crossref_response([item])
        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(request_delay=0, sources={"research_square": "10.21203"}) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert papers[0]["abstract"] == "Clean abstract."


class TestRetry:
    """Tests for CrossrefClient retry handling."""

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        items = [_make_crossref_item()]
        ok_response = _make_crossref_response(items)
        route = respx.get("https://api.crossref.org/works").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(request_delay=0, sources={"research_square": "10.21203"}) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
        assert len(papers) == 1
        assert route.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_crossref.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ingest.crossref'`

- [ ] **Step 3: Implement the Crossref client**

Create `pipeline/ingest/crossref.py`:

```python
"""Async client for the Crossref API — harvests preprints by DOI prefix.

Covers Research Square (10.21203), ChemRxiv (10.26434), SSRN (10.2139).

Usage:
    async with CrossrefClient(email="you@example.com") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

from pipeline.http_retry import request_with_retry
from pipeline.models import SourceServer

log = structlog.get_logger()

_DEFAULT_SOURCES: dict[str, str] = {
    "research_square": "10.21203",
    "chemrxiv": "10.26434",
    "ssrn": "10.2139",
}

_SOURCE_SERVER_MAP: dict[str, SourceServer] = {
    "research_square": SourceServer.RESEARCH_SQUARE,
    "chemrxiv": SourceServer.CHEMRXIV,
    "ssrn": SourceServer.SSRN,
}

# Regex to strip HTML/JATS tags from abstracts
_TAG_RE = re.compile(r"<[^>]+>")


class CrossrefClient:
    """Async client for Crossref preprint harvest by DOI prefix."""

    BASE_URL = "https://api.crossref.org/works"
    PAGE_SIZE = 100

    def __init__(
        self,
        email: str = "",
        request_delay: float = 1.0,
        max_retries: int = 3,
        sources: dict[str, str] | None = None,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.sources = sources if sources is not None else _DEFAULT_SOURCES
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CrossrefClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts from all configured Crossref sources."""
        for source_name, prefix in self.sources.items():
            async for paper in self._fetch_source(source_name, prefix, from_date, to_date):
                yield paper

    # -- Internal ------------------------------------------------------------

    async def _fetch_source(
        self, source_name: str, prefix: str, from_date: date, to_date: date,
    ) -> AsyncGenerator[dict, None]:
        """Paginate through all results for a single DOI prefix."""
        cursor = "*"
        total_fetched = 0
        while True:
            data = await self._fetch_page(prefix, from_date, to_date, cursor)
            items = data.get("message", {}).get("items", [])
            if not items:
                break

            for item in items:
                yield self._normalise(item, source_name)
            total_fetched += len(items)

            next_cursor = data.get("message", {}).get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            log.info(
                "page_fetched",
                source=f"crossref:{source_name}",
                fetched_so_far=total_fetched,
                total=data.get("message", {}).get("total-results", 0),
            )

    async def _fetch_page(
        self, prefix: str, from_date: date, to_date: date, cursor: str,
    ) -> dict:
        """Fetch a single page from the Crossref API with retry."""
        if self._client is None:
            raise RuntimeError("Use CrossrefClient as async context manager")

        params: dict = {
            "filter": (
                f"prefix:{prefix},"
                f"type:posted-content,"
                f"from-posted-date:{from_date},"
                f"until-posted-date:{to_date}"
            ),
            "rows": self.PAGE_SIZE,
            "cursor": cursor,
            "sort": "posted",
            "order": "desc",
        }
        if self.email:
            params["mailto"] = self.email

        resp = await request_with_retry(
            self._client,
            self.BASE_URL,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source=f"crossref:{prefix}",
        )
        if resp is None:
            raise RuntimeError(f"Crossref returned unexpected None response for {prefix}")
        return resp.json()

    def _normalise(self, raw: dict, source_name: str) -> dict:
        """Map a Crossref work item to the common metadata schema."""
        titles = raw.get("title", [])
        title = titles[0].strip() if titles else ""

        authors = []
        for author in raw.get("author", []):
            family = author.get("family", "")
            given = author.get("given", "")
            if given:
                authors.append({"name": f"{family}, {given}"})
            else:
                authors.append({"name": family})

        abstract_raw = raw.get("abstract", "")
        abstract = _TAG_RE.sub("", abstract_raw).strip()

        # Parse posted date — may be [year, month, day], [year, month], or [year]
        date_parts = raw.get("posted", {}).get("date-parts", [[]])
        parts = date_parts[0] if date_parts else []
        year = parts[0] if len(parts) >= 1 else 2000
        month = parts[1] if len(parts) >= 2 else 1
        day = parts[2] if len(parts) >= 3 else 1
        posted_date = date(year, month, day)

        # Extract version from DOI suffix (e.g., /v3)
        doi = raw.get("DOI", "")
        version = 1
        version_match = re.search(r"/v(\d+)$", doi)
        if version_match:
            version = int(version_match.group(1))

        source_server = _SOURCE_SERVER_MAP.get(source_name, SourceServer.RESEARCH_SQUARE)

        return {
            "doi": doi or None,
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": abstract,
            "source_server": source_server,
            "posted_date": posted_date,
            "subject_category": None,
            "version": version,
            "full_text_url": None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_crossref.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/crossref.py tests/test_crossref.py
git commit -m "feat: add Crossref ingest client for Research Square, ChemRxiv, SSRN"
```

---

### Task 3: Zenodo Ingest Client

**Files:**
- Create: `pipeline/ingest/zenodo.py`
- Create: `tests/test_zenodo.py`

Zenodo REST API at `https://zenodo.org/api/records` with `type=publication&subtype=preprint` filter. Page-based pagination.

- [ ] **Step 1: Write tests**

Create `tests/test_zenodo.py`:

```python
"""Tests for pipeline.ingest.zenodo — Zenodo API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx


def _make_client(**kwargs):
    from pipeline.ingest.zenodo import ZenodoClient
    return ZenodoClient(request_delay=0, **kwargs)


def _make_zenodo_hit(
    doi: str = "10.5281/zenodo.1234567",
    title: str = "Test Zenodo Preprint",
    creators: list[dict] | None = None,
    description: str = "A test abstract from Zenodo.",
    pub_date: str = "2026-03-15",
    subjects: list[dict] | None = None,
) -> dict:
    """Create a Zenodo record hit matching the real API format."""
    if creators is None:
        creators = [{"name": "Smith, Alice", "orcid": "0000-0001-2345-6789"}]
    hit: dict = {
        "doi": doi,
        "metadata": {
            "title": title,
            "creators": creators,
            "description": description,
            "publication_date": pub_date,
        },
        "links": {
            "html": f"https://zenodo.org/records/{doi.split('.')[-1]}",
        },
    }
    if subjects:
        hit["metadata"]["subjects"] = subjects
    return hit


def _make_zenodo_response(hits: list[dict], total: int | None = None) -> dict:
    """Wrap hits in the Zenodo API response envelope."""
    return {
        "hits": {
            "total": total if total is not None else len(hits),
            "hits": hits,
        },
    }


class TestNormalise:
    """Tests for ZenodoClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        hit = _make_zenodo_hit(
            doi="10.5281/zenodo.9999",
            title="  Zenodo Paper Title  ",
            creators=[
                {"name": "Smith, Alice"},
                {"name": "Jones, Bob"},
            ],
            description="<p>Abstract with <em>HTML</em>.</p>",
            pub_date="2026-03-15",
        )
        result = client._normalise(hit)

        assert result["doi"] == "10.5281/zenodo.9999"
        assert result["title"] == "Zenodo Paper Title"
        assert result["authors"] == [{"name": "Smith, Alice"}, {"name": "Jones, Bob"}]
        assert result["abstract"] == "Abstract with HTML."
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "zenodo"
        assert result["version"] == 1

    def test_missing_description(self):
        client = _make_client()
        hit = _make_zenodo_hit()
        del hit["metadata"]["description"]
        result = client._normalise(hit)
        assert result["abstract"] == ""

    def test_subject_category(self):
        client = _make_client()
        hit = _make_zenodo_hit(subjects=[{"term": "Molecular Biology"}])
        result = client._normalise(hit)
        assert result["subject_category"] == "Molecular Biology"


class TestFetch:
    """Tests for ZenodoClient.fetch_papers — HTTP pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        hits = [_make_zenodo_hit(doi=f"10.5281/zenodo.{i}") for i in range(3)]
        response = _make_zenodo_response(hits)
        respx.get("https://zenodo.org/api/records").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 3
        assert all(p["source_server"] == "zenodo" for p in papers)

    @respx.mock
    async def test_fetch_empty(self):
        response = _make_zenodo_response([], total=0)
        respx.get("https://zenodo.org/api/records").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_retry_on_503(self):
        hits = [_make_zenodo_hit()]
        ok_response = _make_zenodo_response(hits)
        route = respx.get("https://zenodo.org/api/records").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
        assert len(papers) == 1
        assert route.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_zenodo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ingest.zenodo'`

- [ ] **Step 3: Implement the Zenodo client**

Create `pipeline/ingest/zenodo.py`:

```python
"""Async client for the Zenodo REST API.

Usage:
    async with ZenodoClient() as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

from pipeline.http_retry import request_with_retry
from pipeline.models import SourceServer

log = structlog.get_logger()

_TAG_RE = re.compile(r"<[^>]+>")


class ZenodoClient:
    """Async client for Zenodo preprint search."""

    BASE_URL = "https://zenodo.org/api/records"
    PAGE_SIZE = 100

    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ZenodoClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts from Zenodo preprints."""
        page = 1
        while True:
            data = await self._fetch_page(from_date, to_date, page)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                yield self._normalise(hit)

            if len(hits) < self.PAGE_SIZE:
                break
            page += 1

            log.info(
                "page_fetched",
                source="zenodo",
                page=page,
                total=data.get("hits", {}).get("total", 0),
                fetched_this_page=len(hits),
            )

    # -- Internal ------------------------------------------------------------

    async def _fetch_page(self, from_date: date, to_date: date, page: int) -> dict:
        """Fetch a single page from the Zenodo API with retry."""
        if self._client is None:
            raise RuntimeError("Use ZenodoClient as async context manager")

        params = {
            "type": "publication",
            "subtype": "preprint",
            "q": f"created:[{from_date} TO {to_date}]",
            "size": self.PAGE_SIZE,
            "page": page,
            "sort": "-created",
        }

        resp = await request_with_retry(
            self._client,
            self.BASE_URL,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source="zenodo",
        )
        if resp is None:
            raise RuntimeError("Zenodo returned unexpected None response")
        return resp.json()

    def _normalise(self, hit: dict) -> dict:
        """Map a Zenodo record hit to the common metadata schema."""
        metadata = hit.get("metadata", {})

        title = metadata.get("title", "").strip()

        creators = metadata.get("creators", [])
        authors = [{"name": c.get("name", "")} for c in creators]

        description_raw = metadata.get("description", "")
        abstract = _TAG_RE.sub("", description_raw).strip()

        pub_date_str = metadata.get("publication_date", "")
        posted_date = date.fromisoformat(pub_date_str) if pub_date_str else date.today()

        subjects = metadata.get("subjects", [])
        subject_category = subjects[0].get("term") if subjects else None

        return {
            "doi": hit.get("doi"),
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": abstract,
            "source_server": SourceServer.ZENODO,
            "posted_date": posted_date,
            "subject_category": subject_category,
            "version": 1,
            "full_text_url": None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_zenodo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/zenodo.py tests/test_zenodo.py
git commit -m "feat: add Zenodo ingest client for preprint harvest"
```

---

### Task 4: Orchestrator + Config Integration

**Files:**
- Modify: `pipeline/config.py:46-51` (add new rate limit settings)
- Modify: `pipeline/orchestrator.py:22-26` (add imports)
- Modify: `pipeline/orchestrator.py:522-548` (add sources to list)

Wire all three new clients into the pipeline.

- [ ] **Step 1: Add config settings**

Add to `pipeline/config.py` after line 51 (`fulltext_request_delay`):

```python
    # Tier 2 source rate limits
    arxiv_request_delay: float = 3.0  # arXiv recommends >= 3s between requests
    crossref_request_delay: float = 1.0
    crossref_email: str = ""  # for polite pool access
    zenodo_request_delay: float = 1.0
```

- [ ] **Step 2: Add imports to orchestrator**

Add to `pipeline/orchestrator.py` imports (after the PubmedClient import on line 25):

```python
from pipeline.ingest.arxiv import ArxivClient
from pipeline.ingest.crossref import CrossrefClient
from pipeline.ingest.zenodo import ZenodoClient
```

- [ ] **Step 3: Register new sources in _run_ingest**

Add to the `sources` list in `pipeline/orchestrator.py` (after the pubmed entry, inside the list at ~line 547):

```python
        (
            "arxiv",
            lambda: ArxivClient(
                request_delay=settings.arxiv_request_delay,
            ),
        ),
        (
            "crossref",
            lambda: CrossrefClient(
                email=settings.crossref_email,
                request_delay=settings.crossref_request_delay,
            ),
        ),
        (
            "zenodo",
            lambda: ZenodoClient(
                request_delay=settings.zenodo_request_delay,
            ),
        ),
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS, no import errors

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py pipeline/orchestrator.py
git commit -m "feat: integrate arXiv, Crossref, Zenodo clients into pipeline orchestrator"
```

---

### Task 5: Medium-Severity Fix — React.memo on Analytics Charts

**Files:**
- Modify: `dashboard/components/analytics-charts.tsx:54`

Wrap `AnalyticsCharts` with `React.memo` to prevent unnecessary re-renders.

- [ ] **Step 1: Add React.memo wrapper**

In `dashboard/components/analytics-charts.tsx`, change the export at line 54 from:

```typescript
export function AnalyticsCharts({
```

to a named function with a memo export. At the top of the file, add `import { memo } from "react";`. Then at line 54, change:

```typescript
function AnalyticsChartsInner({
```

And at the end of the file (after the closing brace of the component), add:

```typescript
export const AnalyticsCharts = memo(AnalyticsChartsInner);
```

- [ ] **Step 2: Verify build**

Run: `cd dashboard && npx next build --no-lint 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/analytics-charts.tsx
git commit -m "perf: wrap AnalyticsCharts in React.memo to prevent unnecessary re-renders"
```

---

### Task 6: Medium-Severity Fix — Optimise totalIngested Query

**Files:**
- Modify: `dashboard/lib/queries/papers.ts:269-271` (Prisma path)
- Modify: `dashboard/lib/queries/papers.ts:431-434` (raw SQL path)

The `totalIngested` count runs as a separate query on every request. In the Prisma path it already runs in `Promise.all` — good. In the raw SQL path it runs independently after the main query. Combine it into the existing count query with a CASE expression.

- [ ] **Step 1: Optimise raw SQL path**

In `dashboard/lib/queries/papers.ts`, replace the separate `totalIngestedResult` query (lines 431-434) by merging it into the existing count query. Change the count query (around line 400) from:

```typescript
  const countResult = await prisma.$queryRaw<[{ count: bigint }]>`
    SELECT COUNT(*) as count FROM papers
    WHERE is_duplicate_of IS NULL
      ${searchClause}
      ${tierClause}
      ${sourceClause}
      ${statusClause}
      ${needsReviewClause}
      ${dimClause}
  `;
  const total = Number(countResult[0].count);
```

to a combined query:

```typescript
  const countResult = await prisma.$queryRaw<[{ count: bigint; total_ingested: bigint }]>`
    SELECT
      COUNT(*) FILTER (WHERE TRUE ${searchClause} ${tierClause} ${sourceClause} ${statusClause} ${needsReviewClause} ${dimClause}) as count,
      COUNT(*) as total_ingested
    FROM papers
    WHERE is_duplicate_of IS NULL
  `;
  const total = Number(countResult[0].count);
  const totalIngested = Number(countResult[0].total_ingested);
```

Then remove the standalone `totalIngestedResult` query block (lines 431-434) and use the already-computed `totalIngested` variable in the return object.

**Note:** This approach combines both counts into one table scan. Verify the Prisma tagged template SQL handles the FILTER clause correctly — if not, fall back to a subquery approach.

- [ ] **Step 2: Verify build**

Run: `cd dashboard && npx next build --no-lint 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/lib/queries/papers.ts
git commit -m "perf: combine totalIngested count into single query to eliminate extra table scan"
```

---

### Task 7: Database Backup/Restore Scripts

**Files:**
- Create: `scripts/backup_db.py`
- Create: `scripts/restore_db.py`

Simple `pg_dump`/`pg_restore` wrappers with timestamped filenames, retention policy, and optional compression.

- [ ] **Step 1: Create backup script**

Create `scripts/backup_db.py`:

```python
#!/usr/bin/env python3
"""Database backup using pg_dump.

Usage:
    python scripts/backup_db.py                    # Backup to ./backups/
    python scripts/backup_db.py --dir /mnt/backups # Custom directory
    python scripts/backup_db.py --keep 30          # Retain last 30 days (default: 14)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()


def _parse_database_url(url: str) -> dict[str, str]:
    """Extract host, port, dbname, user, password from a DATABASE_URL."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def backup(database_url: str, backup_dir: Path, keep_days: int = 14) -> Path:
    """Run pg_dump and return the path to the backup file."""
    backup_dir.mkdir(parents=True, exist_ok=True)

    db = _parse_database_url(database_url)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"durc_triage_{timestamp}.sql.gz"
    filepath = backup_dir / filename

    env = {"PGPASSWORD": db["password"]} if db["password"] else {}

    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--format=custom",
        f"--file={filepath}",
    ]

    log.info("backup_starting", file=str(filepath), host=db["host"], dbname=db["dbname"])

    result = subprocess.run(cmd, env={**dict(__import__("os").environ), **env}, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("backup_failed", stderr=result.stderr)
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    size_mb = filepath.stat().st_size / (1024 * 1024)
    log.info("backup_complete", file=str(filepath), size_mb=round(size_mb, 2))

    # Prune old backups
    _prune(backup_dir, keep_days)

    return filepath


def _prune(backup_dir: Path, keep_days: int) -> None:
    """Delete backup files older than keep_days."""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    pruned = 0
    for f in sorted(backup_dir.glob("durc_triage_*.sql.gz")):
        if datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) < cutoff:
            f.unlink()
            pruned += 1
    if pruned:
        log.info("backup_pruned", count=pruned, keep_days=keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup DURC triage database")
    parser.add_argument("--dir", default="backups", help="Backup directory (default: ./backups/)")
    parser.add_argument("--keep", type=int, default=14, help="Days to retain backups (default: 14)")
    args = parser.parse_args()

    # Load DATABASE_URL from .env or environment
    from dotenv import load_dotenv
    load_dotenv()

    import os
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    backup(database_url, Path(args.dir), args.keep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create restore script**

Create `scripts/restore_db.py`:

```python
#!/usr/bin/env python3
"""Database restore using pg_restore.

Usage:
    python scripts/restore_db.py backups/durc_triage_20260409_060000.sql.gz
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()


def _parse_database_url(url: str) -> dict[str, str]:
    """Extract host, port, dbname, user, password from a DATABASE_URL."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def restore(database_url: str, backup_file: Path) -> None:
    """Run pg_restore from a backup file."""
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    db = _parse_database_url(database_url)
    env = {"PGPASSWORD": db["password"]} if db["password"] else {}

    cmd = [
        "pg_restore",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--clean",
        "--if-exists",
        "--no-owner",
        str(backup_file),
    ]

    log.info("restore_starting", file=str(backup_file), host=db["host"], dbname=db["dbname"])

    result = subprocess.run(cmd, env={**dict(__import__("os").environ), **env}, capture_output=True, text=True)
    if result.returncode != 0 and "ERROR" in result.stderr:
        log.error("restore_failed", stderr=result.stderr)
        raise RuntimeError(f"pg_restore failed: {result.stderr}")

    log.info("restore_complete", file=str(backup_file))


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore DURC triage database from backup")
    parser.add_argument("file", type=Path, help="Path to backup file (.sql.gz)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    import os
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    restore(database_url, args.file)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify scripts are importable (no syntax errors)**

Run: `python -c "import scripts.backup_db; import scripts.restore_db; print('OK')"`
Expected: `OK` (or adjust to `python -c "exec(open('scripts/backup_db.py').read())"` if not on sys.path)

- [ ] **Step 4: Commit**

```bash
git add scripts/backup_db.py scripts/restore_db.py
git commit -m "feat: add database backup/restore scripts with retention policy"
```

---

### Task 8: Frontend Test Framework (Vitest)

**Files:**
- Modify: `dashboard/package.json` (add dev dependencies)
- Create: `dashboard/vitest.config.ts`
- Create: `dashboard/lib/__tests__/utils.test.ts`

Bootstrap Vitest with happy-dom and write initial unit tests for `lib/utils.ts`.

- [ ] **Step 1: Install test dependencies**

Run:

```bash
cd dashboard && npm install --save-dev vitest @testing-library/react @testing-library/jest-dom @vitejs/plugin-react happy-dom
```

- [ ] **Step 2: Create Vitest config**

Create `dashboard/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname),
    },
  },
  test: {
    environment: "happy-dom",
    include: ["**/__tests__/**/*.test.{ts,tsx}", "**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
    setupFiles: [],
  },
});
```

- [ ] **Step 3: Add test script to package.json**

Add to `dashboard/package.json` scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 4: Write unit tests for lib/utils.ts**

Create `dashboard/lib/__tests__/utils.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  formatDate,
  formatDuration,
  formatCost,
  parseDimensions,
  languageName,
  sourceServerLabel,
} from "../utils";

describe("formatDate", () => {
  it("formats a Date object", () => {
    const result = formatDate(new Date("2026-03-15"));
    expect(result).toContain("Mar");
    expect(result).toContain("15");
    expect(result).toContain("2026");
  });

  it("formats a date string", () => {
    const result = formatDate("2026-03-15");
    expect(result).toContain("2026");
  });
});

describe("formatDuration", () => {
  it("returns seconds for short durations", () => {
    const start = "2026-03-15T10:00:00Z";
    const end = "2026-03-15T10:00:45Z";
    expect(formatDuration(start, end)).toBe("45s");
  });

  it("returns minutes and seconds for longer durations", () => {
    const start = "2026-03-15T10:00:00Z";
    const end = "2026-03-15T10:02:30Z";
    expect(formatDuration(start, end)).toBe("2m 30s");
  });

  it("returns Running... when end is null", () => {
    expect(formatDuration("2026-03-15T10:00:00Z", null)).toBe("Running...");
  });
});

describe("formatCost", () => {
  it("formats to two decimal places", () => {
    expect(formatCost(1.5)).toBe("$1.50");
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(123.456)).toBe("$123.46");
  });
});

describe("parseDimensions", () => {
  it("returns empty object for null/undefined", () => {
    expect(parseDimensions(null)).toEqual({});
    expect(parseDimensions(undefined)).toEqual({});
  });

  it("returns object as-is if already parsed", () => {
    const dims = { pathogen_enhancement: { score: 2, justification: "test" } };
    expect(parseDimensions(dims)).toEqual(dims);
  });

  it("parses a valid JSON string", () => {
    const json = '{"pathogen_enhancement": {"score": 1, "justification": "low"}}';
    const result = parseDimensions(json);
    expect(result.pathogen_enhancement.score).toBe(1);
  });

  it("handles trailing commas in JSON", () => {
    const json = '{"key": {"score": 1, "justification": "test",},}';
    const result = parseDimensions(json);
    expect(result.key.score).toBe(1);
  });

  it("returns empty object for invalid JSON", () => {
    expect(parseDimensions("not json at all")).toEqual({});
  });

  it("returns empty object for arrays", () => {
    expect(parseDimensions([1, 2, 3])).toEqual({});
  });
});

describe("languageName", () => {
  it("maps known codes", () => {
    expect(languageName("chi")).toBe("Chinese");
    expect(languageName("jpn")).toBe("Japanese");
    expect(languageName("spa")).toBe("Spanish");
  });

  it("uppercases unknown codes", () => {
    expect(languageName("xyz")).toBe("XYZ");
  });

  it("is case-insensitive", () => {
    expect(languageName("CHI")).toBe("Chinese");
  });
});

describe("sourceServerLabel", () => {
  it("returns human-readable labels", () => {
    expect(sourceServerLabel("biorxiv")).toBe("bioRxiv");
    expect(sourceServerLabel("medrxiv")).toBe("medRxiv");
    expect(sourceServerLabel("europepmc")).toBe("Europe PMC");
    expect(sourceServerLabel("arxiv")).toBe("arXiv");
    expect(sourceServerLabel("research_square")).toBe("Research Square");
    expect(sourceServerLabel("chemrxiv")).toBe("ChemRxiv");
    expect(sourceServerLabel("zenodo")).toBe("Zenodo");
    expect(sourceServerLabel("ssrn")).toBe("SSRN");
  });

  it("returns raw string for unknown servers", () => {
    expect(sourceServerLabel("unknown")).toBe("unknown");
  });
});
```

- [ ] **Step 5: Run tests**

Run: `cd dashboard && npx vitest run`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/vitest.config.ts dashboard/lib/__tests__/utils.test.ts dashboard/package.json dashboard/package-lock.json
git commit -m "feat: bootstrap Vitest test framework with lib/utils unit tests"
```

---

### Task 9: Update ROADMAP.md

**Files:**
- Modify: `ROADMAP.md`

Mark Batch 4 items as complete and update status.

- [ ] **Step 1: Update ROADMAP.md**

Move Batch 4 items from Upcoming to Completed. Mark the medium-severity fixes. Update:

```markdown
### Batch 4 — Coverage expansion and hardening

- [x] **#14** Tier 2 ingest clients: arXiv (q-bio), Crossref (Research Square, ChemRxiv, SSRN), Zenodo
- [x] **#15** Frontend test framework (Vitest unit tests for lib/utils)
- [x] **#16** Database backup/restore scripts with retention policy
- [x] React.memo on AnalyticsCharts (audit medium-severity)
- [x] Optimise totalIngested count query (audit medium-severity)
```

- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "chore: update roadmap — mark batch 4 complete"
```
