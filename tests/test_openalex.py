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

        respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(404))

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
        respx.get("https://api.openalex.org/authors/A1111").mock(return_value=httpx.Response(500))
        respx.get("https://api.openalex.org/authors/A2222").mock(return_value=httpx.Response(500))

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
