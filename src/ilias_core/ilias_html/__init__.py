"""Parser modules for ILIAS HTML pages (S7/S8).

Pure functions: HTML string + base_url → dataclasses/dicts.
One module per page type under src/ilias_core/ilias_html/.
Selectors as central constants with fallbacks.
"""

from __future__ import annotations

__all__ = [
    "parse_link",
    "parse_container",
    "parse_memberships",
    "parse_size",
    "parse_date",
]