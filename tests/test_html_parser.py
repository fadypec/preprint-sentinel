"""Tests for pipeline.fulltext.html_parser — HTML methods extraction."""

from __future__ import annotations


def _make_html(body_html: str) -> bytes:
    """Wrap body HTML in a minimal page structure."""
    return f"""\
<html><head><title>Test</title></head>
<body>{body_html}</body></html>""".encode()


class TestExtractMethods:
    """Tests for extract_methods function."""

    def test_methods_heading_found(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Introduction</h2><p>Background info.</p>
            <h2>Methods</h2><p>We used CRISPR-Cas9.</p><p>Cells were cultured.</p>
            <h2>Results</h2><p>Editing was successful.</p>
        """)
        full_text, methods = extract_methods(html)
        assert "CRISPR-Cas9" in methods
        assert "Cells were cultured." in methods
        assert "Background info." not in methods
        assert "Editing was successful." not in methods

    def test_materials_and_methods_heading(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Materials and Methods</h2><p>PCR was performed.</p>
            <h2>Results</h2><p>Bands observed.</p>
        """)
        _, methods = extract_methods(html)
        assert "PCR was performed." in methods

    def test_no_methods_heading_returns_full_text(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Introduction</h2><p>Some intro.</p>
            <h2>Results</h2><p>Some results.</p>
        """)
        full_text, methods = extract_methods(html)
        assert "Some intro." in methods
        assert "Some results." in methods
        assert full_text == methods

    def test_script_and_style_stripped(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <script>var x = 1;</script>
            <style>body { color: red; }</style>
            <h2>Methods</h2><p>Real content here.</p>
            <h2>Results</h2><p>More content.</p>
        """)
        _, methods = extract_methods(html)
        assert "var x" not in methods
        assert "color: red" not in methods
        assert "Real content here." in methods

    def test_nav_header_footer_stripped(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <nav><a href="/">Home</a></nav>
            <header><p>Site header</p></header>
            <h2>Methods</h2><p>Experiment details.</p>
            <h2>Results</h2><p>Data.</p>
            <footer><p>Copyright 2026</p></footer>
        """)
        full_text, methods = extract_methods(html)
        assert "Home" not in full_text
        assert "Site header" not in full_text
        assert "Copyright" not in full_text
        assert "Experiment details." in methods

    def test_h3_heading_also_detected(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h3>Introduction</h3><p>Intro.</p>
            <h3>Experimental Procedures</h3><p>Western blot.</p>
            <h3>Results</h3><p>Bands.</p>
        """)
        _, methods = extract_methods(html)
        assert "Western blot." in methods
        assert "Intro." not in methods
