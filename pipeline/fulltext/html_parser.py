"""HTML fallback methods section extraction.

Used when full text is available only as HTML (e.g., from Unpaywall).
Identifies the methods section by heading text, similar to the JATS parser.
"""

from __future__ import annotations

import re

from lxml import html as lxml_html

# Same heading patterns as the JATS parser
# Optional leading section number: "4 Methods", "4. Methods", "IV. Methods", etc.
_SECTION_NUM_PREFIX = r"(?:[\dIVXivx]+\.?\s+)?"
_METHODS_CORE = (
    r"materials?\s*(?:and|&)\s*methods"
    r"|methods?\s*(?:details|summary|section)?"
    r"|experimental\s*(?:procedures|methods|model\s*details|design)"
    r"|study\s*methods"
    r"|star\s*methods"
    r"|online\s*methods"
    r"|supplementa(?:l|ry)\s*experimental\s*procedures"
)
_METHODS_HEADINGS = re.compile(
    _SECTION_NUM_PREFIX + r"(" + _METHODS_CORE + r")$",
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

    # Strategy 1: Look for heading tags (h1-h6, not just h1-h4)
    methods_section = _extract_by_headings(body)
    if methods_section:
        return (full_text, methods_section)

    # Strategy 2: Look for div/section elements with method-like content
    methods_section = _extract_by_content_structure(body)
    if methods_section:
        return (full_text, methods_section)

    # Strategy 3: Publisher-specific patterns
    methods_section = _extract_by_publisher_patterns(body)
    if methods_section:
        return (full_text, methods_section)

    # Strategy 4: Plain text/paragraph-based patterns
    methods_section = _extract_by_paragraph_patterns(body)
    if methods_section:
        return (full_text, methods_section)

    return (full_text, full_text)


# Additional headings that are methods-adjacent (Cell/Elsevier STAR Methods pattern)
_METHODS_ADJACENT = re.compile(
    r"^(?:[\dIVXivx]+\.?\s+)?"
    r"(quantification\s*(?:and|&)\s*statistical\s*analysis"
    r"|resource\s*availability"
    r"|key\s*resources?\s*table"
    r"|reagents?\s*(?:and|&)\s*tools)"
    r"$",
    re.IGNORECASE,
)


def _extract_by_headings(body) -> str | None:
    """Extract methods using h1-h6 heading tags.

    Collects all consecutive methods-related sections (handles Cell/Elsevier
    papers that split methods into "Experimental model details",
    "Method details", "Quantification and statistical analysis", etc.).
    """
    collected_parts: list[str] = []
    in_methods_zone = False
    methods_level: int | None = None  # heading level (1-6) of the first methods match

    for heading in body.iter("h1", "h2", "h3", "h4", "h5", "h6"):
        try:
            heading_text = heading.text_content().strip()
        except (ValueError, TypeError):
            continue

        heading_level = int(heading.tag[1])

        # Skip sub-headings when collecting methods sections
        if in_methods_zone and methods_level is not None and heading_level > methods_level:
            continue

        is_methods = _METHODS_HEADINGS.match(heading_text)
        is_adjacent = _METHODS_ADJACENT.match(heading_text)

        if is_methods:
            in_methods_zone = True
            if methods_level is None:
                methods_level = heading_level
            section_text = _extract_section_by_siblings(heading)
            if section_text:
                collected_parts.append(section_text)
        elif in_methods_zone and is_adjacent:
            # Continue collecting adjacent methods sections
            section_text = _extract_section_by_siblings(heading)
            if section_text:
                collected_parts.append(section_text)
        elif in_methods_zone:
            # Hit a non-methods heading at the same level — stop collecting
            break

    if collected_parts:
        combined = " ".join(collected_parts)
        full_len = len(body.text_content() or "")
        if len(combined) < full_len:
            return combined

    return None


def _extract_by_content_structure(body) -> str | None:
    """Extract methods from div/section elements or structured content."""
    # Look for div or section elements containing methods-like content
    for elem in body.iter("div", "section", "article"):
        elem_text = elem.text_content().strip()
        if len(elem_text) < 100:  # Skip very short elements
            continue

        # Check if this element starts with a methods heading pattern
        first_lines = elem_text[:500]
        if _METHODS_HEADINGS.search(first_lines):
            # Extract from start of methods pattern to end of element

            match = _METHODS_HEADINGS.search(elem_text)
            if match:
                methods_start = match.start()
                methods_text = elem_text[methods_start:].strip()
                # Sanity check - should be substantial but not the entire document
                if 200 < len(methods_text) < len(elem_text) * 0.8:
                    return methods_text

    return None


def _extract_by_publisher_patterns(body) -> str | None:
    """Extract using publisher-specific patterns."""
    full_text = body.text_content()

    # Pattern 1: Nature/Springer - often uses "Methods" in plain text followed by content
    _next_sections = (
        r"Results|Discussion|References|Data availability"
        r"|Author information|Acknowledgements|Extended data"
    )
    nature_pattern = re.compile(
        rf"\n\s*Methods\s*\n(.*?)(?=\n\s*(?:{_next_sections})\s*\n|$)",
        re.DOTALL | re.IGNORECASE,
    )
    match = nature_pattern.search(full_text)
    if match and len(match.group(1).strip()) > 100:
        return f"Methods\n{match.group(1).strip()}"

    # Pattern 2: Look for numbered sections
    numbered_pattern = re.compile(
        r"\n\s*(\d+\.?\s*(?:Materials?\s*(?:and|&)\s*)?Methods?)\s*\n(.*?)(?=\n\s*\d+\.?\s*\w|$)",
        re.DOTALL | re.IGNORECASE,
    )
    match = numbered_pattern.search(full_text)
    if match and len(match.group(2).strip()) > 100:
        return f"{match.group(1)}\n{match.group(2).strip()}"

    return None


def _extract_by_paragraph_patterns(body) -> str | None:
    """Extract methods from paragraph-style patterns (e.g., Nature journals)."""
    # Look for paragraphs that are just "Methods" followed by methods content
    for elem in body.iter("p"):
        elem_text = elem.text_content().strip()

        # Check if this paragraph is just "Methods" or "Materials and Methods"
        if _METHODS_HEADINGS.match(elem_text):
            # Collect subsequent paragraphs until we hit another section
            parts = [elem_text]
            next_elem = elem.getnext()

            while next_elem is not None:
                next_text = next_elem.text_content().strip()

                # Stop at next major section
                if len(next_text) < 50 and re.match(
                    r"^\s*(results|discussion|conclusions?|acknowledgements?|references)\s*$",
                    next_text,
                    re.IGNORECASE,
                ):
                    break

                parts.append(next_text)
                next_elem = next_elem.getnext()

                # Stop after reasonable amount of content
                if len(" ".join(parts)) > 5000:
                    break

            methods_text = " ".join(parts)
            # Sanity check - should be substantial but not everything
            if 100 < len(methods_text) < len(body.text_content()) * 0.8:
                return methods_text

    return None


def _extract_section_by_siblings(heading) -> str:
    """Extract section content using sibling traversal."""
    heading_tag = heading.tag
    heading_level = int(heading_tag[1]) if heading_tag[1:].isdigit() else 999

    parts = [heading.text_content().strip()]
    sibling = heading.getnext()

    while sibling is not None:
        # Stop at same or higher level heading
        if (
            sibling.tag in ["h1", "h2", "h3", "h4", "h5", "h6"]
            and int(sibling.tag[1]) <= heading_level
        ):
            break
        parts.append(_extract_text(sibling))
        sibling = sibling.getnext()

    return " ".join(parts)
