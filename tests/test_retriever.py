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
<p>This paper describes a novel method for analyzing biological
samples using advanced molecular techniques and bioinformatics.</p>
<p>The approach builds on previous work by Smith et al. and
extends the framework with improved sensitivity metrics.</p>
<p>Our hypothesis is that this method provides more accurate
results than existing gel-based approaches in the field.</p>
<p>We evaluated performance across multiple sample types
including tissue, blood, and environmental specimens.</p>
<p>The motivation for this work stems from limitations in
current protocols that require large sample volumes.</p>
</sec>
<sec sec-type="methods"><title>Methods</title>
<p>We used PCR followed by gel electrophoresis to analyze
DNA extracted from 50 subjects across three cohorts.</p>
<p>Sample collection followed standard protocols with
appropriate informed consent from all participants.</p>
<p>Statistical analysis was performed using R software with significance set at p&lt;0.05.</p>
<p>All experiments were conducted in triplicate and results averaged for analysis.</p>
</sec>
<sec><title>Results</title>
<p>The method amplified target sequences in 47 of 50
samples giving a 94 percent success rate overall.</p>
<p>No significant differences were observed between
the treatment groups with a p-value of 0.23.</p>
<p>Quality control samples performed within expected
ranges throughout the duration of the study period.</p>
<p>Sensitivity analysis confirmed robust performance
across varying input concentrations and conditions.</p>
<p>Reproducibility was high with coefficient of
variation below 5 percent for all measured outcomes.</p>
</sec>
<sec><title>Discussion</title>
<p>These results demonstrate the effectiveness of
the new approach for biological sample analysis.</p>
<p>Further validation studies are needed to confirm
these preliminary findings in larger cohorts.</p>
<p>The method shows promise for clinical settings
where rapid turnaround time is essential.</p>
<p>Compared to existing approaches our technique
requires less sample material and fewer reagents.</p>
<p>Future work should explore automation potential
and integration with existing laboratory workflows.</p>
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
        assert "PCR followed by gel electrophoresis" in paper.methods_section
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
        assert "PCR followed by gel electrophoresis" in paper.methods_section

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
