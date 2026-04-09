"""Async client for the ORCID Public API -- author identity and affiliations.

Usage:
    async with OrcidClient() as client:
        result = await client.lookup("Jane Smith", known_orcid="0000-0001-2345-6789")
        if result:
            print(result["current_institution"])
"""

from __future__ import annotations

import httpx
import structlog

from pipeline.http_retry import request_with_retry

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
        if self._client is None:
            raise RuntimeError("Use OrcidClient as async context manager")

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
            given = parts[0]
            family = parts[-1]
            query = f"given-names:{given} AND family-name:{family}"
        else:
            query = f"family-name:{name}"

        url = f"{BASE_URL}/search/"
        params = {"q": query, "rows": 1}

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            source="orcid",
        )
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return None
        orcid_ident = results[0].get("orcid-identifier", {})
        return orcid_ident.get("path")

    async def _fetch_record(self, orcid_id: str) -> dict | None:
        """Fetch the full ORCID record. Returns None on 404."""
        url = f"{BASE_URL}/{orcid_id}/record"

        resp = await request_with_retry(
            self._client,
            url,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            none_on_404=True,
            source="orcid",
        )
        if resp is None:
            return None
        return resp.json()

    def _parse_record(self, orcid_id: str, record: dict) -> dict:
        """Extract structured data from an ORCID record."""
        activities = record.get("activities-summary", {})

        # Employment history
        employment_groups = activities.get("employments", {}).get("affiliation-group", [])
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
        education_groups = activities.get("educations", {}).get("affiliation-group", [])
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
