"""JATS XML methods section extraction.

Extracts the methods section from JATS-formatted full-text articles.
Falls back to the full body text if no methods section is found.
"""

from __future__ import annotations

import re

from lxml import etree

# Heading patterns that indicate a methods section (case-insensitive)
_METHODS_HEADINGS = re.compile(
    r"^(materials?\s*(and|&)\s*methods|methods|experimental\s*(procedures|methods)|study\s*methods)$",
    re.IGNORECASE,
)

# sec-type attribute values that indicate methods
_METHODS_SEC_TYPES = {"methods", "materials|methods", "materials"}


def _extract_text(elem) -> str:
    """Extract all text content from an element, stripping XML tags."""
    return "".join(elem.itertext()).strip()


def extract_methods(xml_bytes: bytes) -> tuple[str, str]:
    """Extract full text and methods section from JATS XML.

    Returns (full_text, methods_section). If no methods section is found,
    both values are the full body text.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_bytes, parser=parser)

    # Extract full body text
    body = root.find(".//body")
    if body is None:
        return ("", "")

    full_text = _extract_text(body)

    # Strategy 1: sec-type attribute
    for sec in body.findall(".//sec"):
        sec_type = sec.get("sec-type", "")
        if sec_type in _METHODS_SEC_TYPES:
            return (full_text, _extract_text(sec))

    # Strategy 2: heading text match
    for sec in body.findall(".//sec"):
        title_elem = sec.find("title")
        if title_elem is not None:
            title_text = _extract_text(title_elem)
            if _METHODS_HEADINGS.match(title_text):
                return (full_text, _extract_text(sec))

    # No methods section found — return full body text for both
    return (full_text, full_text)
