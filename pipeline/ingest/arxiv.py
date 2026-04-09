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
        self, category: str, from_date: date, to_date: date,
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
        self, category: str, from_date: date, to_date: date, start: int,
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
            title = re.sub(r"\s+", " ", title).strip()

            summary = entry_el.findtext("atom:summary", default="", namespaces=_NS)
            summary = re.sub(r"\s+", " ", summary).strip()

            authors = [
                el.findtext("atom:name", default="", namespaces=_NS)
                for el in entry_el.findall("atom:author", _NS)
            ]
            authors = [a for a in authors if a]

            published = entry_el.findtext("atom:published", default="", namespaces=_NS)

            doi = entry_el.findtext("arxiv:doi", default=None, namespaces=_NS)

            primary_cat_el = entry_el.find("arxiv:primary_category", _NS)
            primary_category = (
                primary_cat_el.get("term") if primary_cat_el is not None else None
            )

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
