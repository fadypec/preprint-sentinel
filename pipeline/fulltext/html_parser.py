"""HTML fallback methods section extraction.

Used when full text is available only as HTML (e.g., from Unpaywall).
Identifies the methods section by heading text, similar to the JATS parser.
"""

from __future__ import annotations

import re

from lxml import html as lxml_html

# Same heading patterns as the JATS parser
_METHODS_HEADINGS = re.compile(
    r"^(materials?\s*(and|&)\s*methods|methods|experimental\s*(procedures|methods)|study\s*methods)$",
    re.IGNORECASE,
)

# Elements to strip before text extraction
_STRIP_TAGS = {"script", "style", "nav", "header", "footer"}

# Heading tags to look for
_HEADING_TAGS = {"h1", "h2", "h3", "h4"}


def _clean_tree(tree) -> None:
    """Remove script, style, nav, header, footer elements in-place."""
    # Collect first to avoid iterator invalidation during removal
    to_remove = [elem for elem in tree.iter() if elem.tag in _STRIP_TAGS]
    for elem in to_remove:
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)


def _extract_text(elem) -> str:
    """Extract all text content from an element."""
    return " ".join(elem.text_content().split())


def extract_methods(html_bytes: bytes) -> tuple[str, str]:
    """Extract full text and methods section from HTML.

    Returns (full_text, methods_section). If no methods section is found,
    both values are the full body text.
    """
    doc = lxml_html.fromstring(html_bytes)
    _clean_tree(doc)

    body = doc.find(".//body")
    if body is None:
        body = doc

    full_text = _extract_text(body)

    # Find methods heading
    for heading in body.iter(*_HEADING_TAGS):
        heading_text = heading.text_content().strip()
        if not _METHODS_HEADINGS.match(heading_text):
            continue

        heading_tag = heading.tag
        # Collect all content between this heading and the next heading at the same level
        parts = [heading_text]
        sibling = heading.getnext()
        while sibling is not None:
            if sibling.tag == heading_tag:
                break
            parts.append(_extract_text(sibling))
            sibling = sibling.getnext()

        methods_text = " ".join(parts)
        return (full_text, methods_text)

    return (full_text, full_text)
