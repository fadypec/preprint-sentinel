"""Tests for pipeline.fulltext.jats_parser — JATS XML methods extraction."""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_jats(body_xml: str) -> bytes:
    """Wrap body XML in a minimal JATS article structure."""
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<article><body>{body_xml}</body></article>""".encode()


class TestExtractMethods:
    """Tests for extract_methods function."""

    def test_sec_type_methods(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Intro text.</p></sec>
            <sec sec-type="methods"><title>Methods</title><p>We did CRISPR.</p></sec>
            <sec><title>Results</title><p>It worked.</p></sec>
        """)
        full_text, methods = extract_methods(xml)
        assert "We did CRISPR." in methods
        assert "Intro text." not in methods
        assert "Intro text." in full_text

    def test_sec_type_materials_methods(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec sec-type="materials|methods"><title>Materials and Methods</title>
            <p>Cell culture and reagents.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "Cell culture" in methods

    def test_heading_text_fallback(self):
        """No sec-type attribute but heading text matches."""
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Background.</p></sec>
            <sec><title>Materials and Methods</title><p>PCR amplification.</p></sec>
            <sec><title>Results</title><p>Bands observed.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "PCR amplification." in methods
        assert "Background." not in methods

    def test_experimental_procedures_heading(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Experimental Procedures</title><p>Western blot.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "Western blot." in methods

    def test_no_methods_section_returns_full_body(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Some intro.</p></sec>
            <sec><title>Results</title><p>Some results.</p></sec>
        """)
        full_text, methods = extract_methods(xml)
        assert "Some intro." in methods
        assert "Some results." in methods
        assert full_text == methods

    def test_inline_markup_stripped(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec sec-type="methods"><title>Methods</title>
            <p>We used <italic>E. coli</italic> strain K-12.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "E. coli" in methods
        assert "<italic>" not in methods

    def test_fixture_file(self):
        """Parse the realistic JATS fixture and extract methods."""
        from pipeline.fulltext.jats_parser import extract_methods

        xml_bytes = (FIXTURES_DIR / "sample_jats.xml").read_bytes()
        full_text, methods = extract_methods(xml_bytes)
        assert "serial passage" in methods
        assert "Reverse genetics" in methods
        assert "Introduction" not in methods or "pandemic threat" in full_text
        assert "pandemic threat" in full_text
