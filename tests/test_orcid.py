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
