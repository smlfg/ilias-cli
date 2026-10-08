"""ILIAS HTML Parser Module.

Pure Funktionen für das Parsen von ILIAS-Seiten (keine I/O).
"""

from .links import parse_link, parse_link_with_icon_fallback
from .membership import parse_memberships, has_empty_membership_hint, has_login_marker
from .props import semester_from_title, parse_size, parse_date_german, extract_suffix, SizeResult
from .fetch import fetch_page, FetchResult

__all__ = [
    "parse_link",
    "parse_link_with_icon_fallback",
    "parse_memberships",
    "has_empty_membership_hint",
    "has_login_marker",
    "semester_from_title",
    "parse_size",
    "parse_date_german",
    "extract_suffix",
    "SizeResult",
    "fetch_page",
    "FetchResult",
]