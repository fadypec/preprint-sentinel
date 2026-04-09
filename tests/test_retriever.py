"""Tests for pipeline.fulltext.retriever — full-text retrieval cascade."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import PipelineStage, SourceServer
from tests.conftest import insert_paper

# Expanded JATS with realistic content to pass quality gate
SAMPLE_JATS = b"""\
<?xml version="1.0"?>
<article><body>
<sec><title>Introduction</title>
<p>This paper describes a novel method for analyzing biological samples using molecular techniques.
The approach builds on previous work by Smith et al. and represents a significant advance in the field.</p>
<p>Our hypothesis is that this new method will provide more accurate results than existing approaches.</p>
</sec>
<sec sec-type="methods"><title>Methods</title>
<p>We used PCR amplification followed by gel electrophoresis to analyze DNA samples from 50 subjects.</p>
<p>Sample collection was performed according to standard protocols with appropriate consent procedures.</p>
<p>Statistical analysis was performed using R software with significance set at p&lt;0.05.</p>
<p>All experiments were conducted in triplicate and results averaged for analysis.</p>
</sec>
<sec><title>Results</title>
<p>The method successfully amplified target sequences in 47 of 50 samples (94% success rate).</p>
<p>No significant differences were observed between treatment groups (p=0.23).</p>
<p>Quality control samples performed within expected ranges throughout the study.</p>
</sec>
<sec><title>Discussion</title>
<p>These results demonstrate the effectiveness of the new approach for sample analysis.</p>
<p>Further validation studies are needed to confirm these preliminary findings.</p>
</sec>
</body></article>"""

SAMPLE_HTML = b"""\
<html><body>
<h2>Introduction</h2><p>Background.</p>
<h2>Methods</h2><p>We used Western blot.</p>
<h2>Results</h2><p>Bands.</p>
</body></html>"""


class TestRetrieveCascade:
    """Tests for retrieve_full_text cascade logic."""

    @respx.mock
    async def test_biorxiv_source_succeeds(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1101/2026.03.01.999999",
            source_server=SourceServer.BIORXIV,
        )

        respx.get("https://www.biorxiv.org/content/10.1101/2026.03.01.999999.full.xml").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True
        assert "PCR amplification" in paper.methods_section
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED

    @respx.mock
    async def test_biorxiv_fails_europepmc_succeeds(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1101/2026.03.01.888888",
            source_server=SourceServer.BIORXIV,
        )

        # bioRxiv XML and HTML both return 404
        respx.get("https://www.biorxiv.org/content/10.1101/2026.03.01.888888.full.xml").mock(
            return_value=httpx.Response(404)
        )
        respx.get("https://www.biorxiv.org/content/10.1101/2026.03.01.888888.full").mock(
            return_value=httpx.Response(404)
        )
        # Europe PMC search returns source/id
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(
                200, json={"resultList": {"result": [{"source": "PPR", "id": "PPR999"}]}}
            )
        )
        # Europe PMC full text
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/PPR/PPR999/fullTextXML").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True
        assert "PCR amplification" in paper.methods_section

    @respx.mock
    async def test_all_sources_fail_gracefully(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1234/no-fulltext",
            source_server=SourceServer.PUBMED,
        )

        # Europe PMC returns empty
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        # Unpaywall returns 404
        respx.get("https://api.unpaywall.org/v2/10.1234/no-fulltext").mock(
            return_value=httpx.Response(404)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = "test@test.com"
        settings.unpaywall_request_delay = 0

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is False
        assert paper.methods_section is None
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED

    @respx.mock
    async def test_pmc_source_used_when_available(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1234/pmc-test",
            source_server=SourceServer.PUBMED,
            full_text_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7654321/",
        )

        # Europe PMC returns empty
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        # PMC OA succeeds
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True

    @respx.mock
    async def test_paper_without_doi_goes_straight_to_failure(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi=None,
            source_server=SourceServer.EUROPEPMC,
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is False
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED
