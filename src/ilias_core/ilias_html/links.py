"""Pure link parser for ILIAS HTML anchors.

`parse_link(href, base_url) -> (typ | None, ref_id | None)` according to
spec §13.5: type is determined from the link href, not from the icon.

Selectors are constants with fallbacks so an ILIAS update only touches one place.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants for link type detection (spec §13.5)
# ---------------------------------------------------------------------------

#: Fixed type table mapping link characteristics to ILIAS type names.
#: The order matters: first match wins.  Keys are (lower-case) substrings that
#: may appear in the href or query values.  Case-insensitive.
TYPE_TABLE = [
    # (pattern_lowercase_substring, ilias_type)
    ("cmdclass=ilobjfilegui", "file"),
    ("cmd=sendfile", "file"),
    ("baseclass=ilinkresourcehandlergui", "webr"),
    ("baseclass=ilwikihandlergui", "wiki"),
    ("baseclass=ilexercisehandlergui", "exc"),
    ("cmdclass=ilobjtestgui", "tst"),
    # baseClass=ilrepositorygui without further feature → type from icon fallback
    # (handled by caller returning None → caller uses icon/fallback)
]

#: Types that are container-like (recurse into them in ls)
CONTAINER_TYPES = {"fold", "grp"}

# ---------------------------------------------------------------------------
# Helper: check /go/<typ>/<ref>
# ---------------------------------------------------------------------------

_go_re = re.compile(r"^/go/([a-zA-Z0-9_]+)/(\d+)$")


def _match_go(href: str) -> tuple[str | None, int | None]:
    """Match /go/<typ>/<ref> pattern (spec §13.5, #1)."""
    m = _go_re.match(href)
    if not m:
        return None, None
    typ = m.group(1).lower()
    ref_id = int(m.group(2))
    # Known type mapping from HHN permalinks
    type_map = {
        "crs": "crs",
        "grp": "grp",
        "fold": "fold",
        "exc": "exc",
        "cat": "cat",
        "root": "root",
        "crsr": "crsr",
    }
    ilias_type = type_map.get(typ, typ)  # unknown types keep short name
    return ilias_type, ref_id


# ---------------------------------------------------------------------------
# Helper: parse goto.php/<typ>/<ref>
# ---------------------------------------------------------------------------

def _match_goto_path(href: str) -> tuple[str | None, int | None]:
    """Match goto.php/<typ>/<ref> (spec §13.5, #2)."""
    # Pattern: goto.php/<typ>/<ref>
    m = re.match(r"goto\.php/([a-zA-Z0-9_]+)/(\d+)", href)
    if not m:
        return None, None
    typ = m.group(1).lower()
    ref_id = int(m.group(2))
    # Known type mapping
    type_map = {
        "file": "file",
        "webr": "webr",
        "wiki": "wiki",
        "exc": "exc",
        "tst": "tst",
        "frm": "frm",
        "sess": "sess",
    }
    ilias_type = type_map.get(typ, typ)
    return ilias_type, ref_id


# ---------------------------------------------------------------------------
# Helper: parse goto.php?target=<typ>_<ref>[_download]
# ---------------------------------------------------------------------------

_go_target_re = re.compile(r"goto\.php[?&]target=([a-zA-Z0-9_]+)(?:_download)?")


def _match_goto_target(href: str) -> tuple[str | None, int | None]:
    """Match goto.php?target=<typ>_<ref>[_download] (spec §13.5, #3)."""
    m = _go_target_re.search(href)
    if not m:
        return None, None
    target = m.group(1)
    parts = target.split("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    typ = parts[0].lower()
    ref_id = int(parts[1])
    # Known type mapping
    type_map = {
        "file": "file",
        "webr": "webr",
        "wiki": "wiki",
        "exc": "exc",
        "tst": "tst",
        "frm": "frm",
        "sess": "sess",
    }
    ilias_type = type_map.get(typ, typ)
    return ilias_type, ref_id


# ---------------------------------------------------------------------------
# Helper: parse ilias.php?...ref_id=<ref> with the fixed type table
# ---------------------------------------------------------------------------

_ilias_ref_re = re.compile(r"[?&]ref_id=(\d+)(?:[&#]|$)")


def _match_ilias_ref(href: str) -> tuple[str | None, int | None]:
    """Match ilias.php?...ref_id=<ref> with type table (spec §13.5, #4).

    Returns (typ, ref_id) using the fixed type table.
    If type cannot be determined from the table, returns (None, ref_id)
    — the caller may fall back to the icon.
    """
    m = _ilias_ref_re.search(href)
    if not m:
        return None, None
    ref_id = int(m.group(1))

    href_lower = href.lower()

    # Check the fixed type table (§13.5)
    for pattern, ilias_type in TYPE_TABLE:
        if pattern in href_lower:
            return ilias_type, ref_id

    # Unknown type: keep short name or return None for icon fallback
    # The spec says unknown types → `other` (or their Kürzel) and never loaded
    # But we return None here and let the caller decide; the caller can map to "other"
    return None, ref_id


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def parse_link(href: str, base_url: str) -> tuple[str | None, int | None]:
    """Parse an ILIAS link href and determine type + ref_id.

    According to spec §13.5, the type is determined from the link **href**,
    not from the icon.  The function follows the ordered type table:

    1. /go/<typ>/<ref>                → typ, ref_id
    2. goto.php/<typ>/<ref>           → typ, ref_id
    3. goto.php?target=<typ>_<ref>    → typ, ref_id
    4. ilias.php?...ref_id=<ref>      → typ from table, ref_id (or None, ref_id)

    Unknown types keep their short name (or ``other``) and are **never** loaded.

    ``#`` / empty href → (None, None).

    Returns:
        (typ | None, ref_id | None)
    """
    if not href or href.strip() == "" or href == "#":
        return None, None

    href = href.strip()

    # 1. /go/<typ>/<ref>
    typ, ref_id = _match_go(href)
    if typ is not None:
        return typ, ref_id

    # 2. goto.php/<typ>/<ref>
    typ, ref_id = _match_goto_path(href)
    if typ is not None:
        return typ, ref_id

    # 3. goto.php?target=<typ>_<ref>[_download]
    typ, ref_id = _match_goto_target(href)
    if typ is not None:
        return typ, ref_id

    # 4. ilias.php?...ref_id=<ref> with the fixed type table
    typ, ref_id = _match_ilias_ref(href)
    # Return whatever we found; typ may be None → caller uses icon fallback
    return typ, ref_id