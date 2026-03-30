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
            affil_xml = (
                f"<AffiliationInfo><Affiliation>{affiliation}</Affiliation></AffiliationInfo>"
            )
        author_xml += (
            f"<Author><LastName>{last}</LastName><ForeName>{fore}</ForeName>{affil_xml}</Author>"
        )

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
                pub_year="2026",
                pub_month="3",
                pub_day="15",
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
            _article_xml(
                authors=[
                    ("Rodriguez", "Maria Elena"),
                    ("O'Brien", "Patrick"),
                    ("Li", "X"),
                ]
            )
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
            _article_xml(
                abstract_parts=[
                    ("BACKGROUND", "Viruses are bad."),
                    ("METHODS", "We did science."),
                    ("RESULTS", "It worked."),
                    ("CONCLUSIONS", "Good news."),
                ]
            )
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
        xml = _wrap_articles(_article_xml(abstract_parts=[(None, "A plain abstract.")]))
        articles = client._parse_articles(xml)
        assert articles[0]["abstract"] == "A plain abstract."

    def test_doi_less_article(self):
        """Article without DOI — doi field should be None."""
        client = self._make_client()
        xml = _wrap_articles(_article_xml(doi=None, pmc_id=None))
        articles = client._parse_articles(xml)
        assert articles[0]["doi"] is None
        assert articles[0]["full_text_url"] is None

    def test_pmc_full_text_url(self):
        """Article with PMC ID gets a full-text URL."""
        client = self._make_client()
        xml = _wrap_articles(_article_xml(pmc_id="PMC1234567"))
        articles = client._parse_articles(xml)
        assert (
            articles[0]["full_text_url"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/"
        )

    def test_no_pmc_id_no_url(self):
        """Article without PMC ID — full_text_url is None."""
        client = self._make_client()
        xml = _wrap_articles(_article_xml(doi="10.1234/test", pmc_id=None))
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
        xml = _wrap_articles(_article_xml(mesh_terms=None))
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

    def test_malformed_article_skipped(self):
        """A malformed PubmedArticle is skipped; valid ones still parsed."""
        client = self._make_client()
        malformed = "<PubmedArticle><Garbage/></PubmedArticle>"
        valid = _article_xml(title="Valid Paper")
        xml = _wrap_articles(malformed, valid)
        articles = client._parse_articles(xml)
        assert len(articles) == 1
        assert articles[0]["title"] == "Valid Paper"

    def test_date_fallback_to_today(self):
        """Missing PubMedPubDate falls back to date.today()."""
        client = self._make_client()
        # Build article XML with no History/PubMedPubDate
        xml_str = """<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
    <Article>
      <ArticleTitle>No Date Paper</ArticleTitle>
      <Abstract><AbstractText>Abstract.</AbstractText></Abstract>
      <AuthorList><Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author></AuthorList>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList><ArticleId IdType="doi">10.1/nodate</ArticleId></ArticleIdList>
  </PubmedData>
</PubmedArticle>"""
        articles = client._parse_articles(_wrap_articles(xml_str))
        assert len(articles) == 1
        assert articles[0]["posted_date"] == date.today()


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
            webenv, query_key, count = await client._search(date(2026, 3, 1), date(2026, 3, 1))

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

        async with PubmedClient(request_delay=0, query_mode="mesh_filtered") as client:
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

        async with PubmedClient(request_delay=0, api_key="test_ncbi_key") as client:
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
        respx.get(self.EFETCH_URL).mock(return_value=httpx.Response(200, content=xml))

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
