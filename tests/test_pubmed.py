"""Tests for pipeline.ingest.pubmed — PubMed E-utilities client."""

from __future__ import annotations

from datetime import date

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
