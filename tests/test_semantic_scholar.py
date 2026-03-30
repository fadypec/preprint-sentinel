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

        route = respx.get(
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test"
        ).mock(
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

        route = respx.get(
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test"
        ).mock(
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
