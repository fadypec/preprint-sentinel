"""Async client for the OpenAlex API -- author/institution metadata.

Usage:
    async with OpenAlexClient(email="you@example.com") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result["primary_institution"])
"""

from __future__ import annotations

import httpx
import structlog

from pipeline.http_retry import request_with_retry

log = structlog.get_logger()

BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    """Async client for the OpenAlex API."""

    def __init__(
        self,
        email: str,
        request_delay: float = 0.1,
        max_retries: int = 3,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._external_client = http
        self._client: httpx.AsyncClient | None = http

    async def __aenter__(self) -> OpenAlexClient:
        if self._external_client is None:
            self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._external_client is None and self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> dict | None:
        """Look up a paper by DOI and return enrichment data, or None."""
        if self._client is None:
            raise RuntimeError("Use OpenAlexClient as async context manager")

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
        funder_names = [
            g.get("funder_display_name", "") for g in grants if g.get("funder_display_name")
        ]

        # Extract author data
        authorships = work.get("authorships", [])
        authors = []
        primary_institution = None
        primary_institution_country = None

        # Batch-fetch author details: collect all author IDs, then request in
        # batches of up to 50 via the /authors?filter=openalex:ID1|ID2|... endpoint.
        author_ids: list[str] = []
        for authorship in authorships:
            author_data = authorship.get("author", {})
            aid = self._extract_id(author_data.get("id", ""))
            author_ids.append(aid)

        author_details_map = await self._fetch_authors_batch(author_ids)

        for authorship, author_id in zip(authorships, author_ids):
            author_data = authorship.get("author", {})
            institutions = authorship.get("institutions", [])
            first_inst = institutions[0] if institutions else {}

            orcid_raw = author_data.get("orcid")
            orcid = self._extract_orcid(orcid_raw) if orcid_raw else None

            # Look up pre-fetched author stats
            works_count = None
            author_cited = None
            if author_id and author_id in author_details_map:
                author_detail = author_details_map[author_id]
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
        if not doi:
            log.debug("openalex_skip_empty_doi")
            return None
        url = f"{BASE_URL}/works"
        params = {"filter": f"doi:{doi}", "mailto": self.email}

        assert self._client is not None
        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            none_on_404=True,
            source="openalex",
        )
        if resp is None:
            return None
        data = resp.json()
        results = data.get("results", [])
        return results[0] if results else None

    async def _fetch_authors_batch(self, author_ids: list[str]) -> dict[str, dict]:
        """Batch-fetch author details from OpenAlex.

        Requests up to 50 authors per API call using the filter pipe syntax.
        Returns a dict mapping author_id -> author record.
        """
        # Deduplicate and filter empty IDs
        unique_ids = [aid for aid in dict.fromkeys(author_ids) if aid]
        if not unique_ids:
            return {}

        result_map: dict[str, dict] = {}
        batch_size = 50

        for start in range(0, len(unique_ids), batch_size):
            batch = unique_ids[start : start + batch_size]
            filter_value = "|".join(batch)
            url = f"{BASE_URL}/authors"
            params = {
                "filter": f"openalex:{filter_value}",
                "per_page": str(len(batch)),
                "mailto": self.email,
            }
            try:
                assert self._client is not None
                resp = await request_with_retry(
                    self._client,
                    url,
                    params=params,
                    timeout=30.0,
                    request_delay=self.request_delay,
                    max_retries=self.max_retries,
                    none_on_404=True,
                    source="openalex",
                )
                if resp is None:
                    continue
                data = resp.json()
                for author in data.get("results", []):
                    aid = self._extract_id(author.get("id", ""))
                    if aid:
                        result_map[aid] = author
            except Exception as exc:
                log.debug(
                    "openalex_batch_author_error",
                    batch_size=len(batch),
                    error=str(exc),
                )
                # Fall back to individual lookups for this batch
                for aid in batch:
                    if aid not in result_map:
                        detail = await self._fetch_author(aid)
                        if detail is not None:
                            result_map[aid] = detail

        return result_map

    async def _fetch_author(self, author_id: str) -> dict | None:
        """Fetch author detail from OpenAlex. Returns None on any error."""
        url = f"{BASE_URL}/authors/{author_id}"
        params = {"mailto": self.email}
        try:
            assert self._client is not None
            resp = await request_with_retry(
                self._client,
                url,
                params=params,
                timeout=30.0,
                request_delay=self.request_delay,
                max_retries=self.max_retries,
                none_on_404=True,
                source="openalex",
            )
            if resp is None:
                return None
            return resp.json()
        except Exception as exc:
            log.debug("openalex_author_error", author_id=author_id, error=str(exc))
        return None

    @staticmethod
    def _extract_id(openalex_url: str | None) -> str:
        """Extract the short ID from an OpenAlex URL like 'https://openalex.org/W123'."""
        if not openalex_url:
            return ""
        if "/" in openalex_url:
            return openalex_url.rsplit("/", 1)[-1]
        return openalex_url

    @staticmethod
    def _extract_orcid(orcid_url: str) -> str:
        """Extract ORCID ID from URL like 'https://orcid.org/0000-0001-2345-6789'."""
        if "/" in orcid_url:
            return orcid_url.rsplit("/", 1)[-1]
        return orcid_url
