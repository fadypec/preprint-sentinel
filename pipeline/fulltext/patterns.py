"""Shared regex patterns for methods section detection.

Used by jats_parser, html_parser, and retriever modules to identify
methods section headings consistently.
"""

from __future__ import annotations

import re

# Optional leading section number: "4 Methods", "4. Methods", "IV. Methods", etc.
SECTION_NUM_PREFIX = r"(?:[\dIVXivx]+\.?\s+)?"

# Core methods heading alternatives (without anchors — callers add their own)
METHODS_CORE = (
    r"materials?\s*(?:and|&)\s*methods"
    r"|methods?\s*(?:details|summary|section)?"
    r"|experimental\s*(?:procedures|methods|model\s*details|design)"
    r"|study\s*methods"
    r"|star\s*methods"
    r"|online\s*methods"
    r"|supplementa(?:l|ry)\s*experimental\s*procedures"
)

# Pre-compiled regex anchored at end-of-string (for JATS/HTML heading matching)
METHODS_HEADINGS_RE = re.compile(
    SECTION_NUM_PREFIX + r"(" + METHODS_CORE + r")$",
    re.IGNORECASE,
)

# Pre-compiled regex anchored at end-of-line with optional trailing whitespace
# (for plain-text / PDF methods heading detection)
METHODS_HEADING_MULTILINE_RE = re.compile(
    r"^" + SECTION_NUM_PREFIX + r"(" + METHODS_CORE + r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)
