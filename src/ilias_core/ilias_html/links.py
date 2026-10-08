"""Link-Parser für ILIAS: Typ und ref_id aus allen Link-Formen extrahieren.

Spec §13.5: Reihenfolge der Erkennung:
1. /go/<typ>/<ref> (HHN-Permalink)
2. goto.php/<typ>/<ref>
3. goto.php?target=<typ>_<ref>[_download]
4. ilias.php?...ref_id=<ref> mit Typtabelle (case-insensitive Query-Werte)
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse



# Typen aus der Typtabelle (ilias.php?...ref_id=)
REF_ID_TYPE_MAP = {
    "ilobjfilegui": "file",
    "sendfile": "file",
    "illinkresourcehandlergui": "webr",
    "ilwikihandlergui": "wiki",
    "ilexercisehandlergui": "exc",
    "ilobjtestgui": "tst",
}

# Für goto.php?target=<typ>_<ref>[_download]
TARGET_TYPE_PREFIXES = {
    "crs": "crs",
    "grp": "grp",
    "fold": "fold",
    "file": "file",
    "webr": "webr",
    "exc": "exc",
    "tst": "tst",
    "frm": "frm",
    "sess": "sess",
    "wiki": "wiki",
    "htlm": "htlm",
    "copa": "copa",
    "mcst": "mcst",
    "cat": "cat",
    "root": "root",
}


def _extract_from_go_path(path: str, base_url: str) -> tuple[str | None, int | None]:
    """Form 1: /go/<typ>/<ref>"""
    m = re.match(r"^/go/([a-z]+)/(\d+)", path, re.IGNORECASE)
    if not m:
        return None, None
    typ = m.group(1).lower()
    ref_id = int(m.group(2))
    return typ, ref_id


def _extract_from_goto_path(path: str) -> tuple[str | None, int | None]:
    """Form 2: goto.php/<typ>/<ref>"""
    m = re.match(r"^/goto\.php/([a-z]+)/(\d+)", path, re.IGNORECASE)
    if not m:
        return None, None
    typ = m.group(1).lower()
    ref_id = int(m.group(2))
    return typ, ref_id


def _extract_from_goto_target(query: str) -> tuple[str | None, int | None]:
    """Form 3: goto.php?target=<typ>_<ref>[_download]"""
    params = parse_qs(query, keep_blank_values=True)
    target = params.get("target", [""])[0]
    if not target:
        return None, None
    target = target.lower()
    # Remove _download suffix
    if target.endswith("_download"):
        target = target[:-9]
    # Split by underscore: typ_ref
    parts = target.split("_", 1)
    if len(parts) != 2:
        return None, None
    typ, ref_str = parts
    if not ref_str.isdigit():
        return None, None
    ref_id = int(ref_str)
    # Normalize type
    typ = TARGET_TYPE_PREFIXES.get(typ, typ)
    return typ, ref_id


def _extract_from_ilias_ref_id(query: str, base_url: str) -> tuple[str | None, int | None]:
    """Form 4: ilias.php?...ref_id=<ref> mit Typtabelle"""
    params = parse_qs(query, keep_blank_values=True)
    ref_id_str = params.get("ref_id", [""])[0]
    if not ref_id_str.isdigit():
        return None, None
    ref_id = int(ref_id_str)

    # Check for type indicators in query (case-insensitive)
    for key, values in params.items():
        for val in values:
            val_lower = val.lower()
            if val_lower in REF_ID_TYPE_MAP:
                return REF_ID_TYPE_MAP[val_lower], ref_id
            # Also check cmdClass, baseClass, cmd
            if key.lower() in ("cmdclass", "baseclass", "cmd") and val_lower in REF_ID_TYPE_MAP:
                return REF_ID_TYPE_MAP[val_lower], ref_id

    # No type found from query - return ref_id with None type (caller may use icon fallback)
    return None, ref_id


def parse_link(href: str, base_url: str) -> tuple[str | None, int | None]:
    """Parse einen ILIAS-Link und gebe (typ, ref_id) zurück.

    Reihenfolge gemäß Spec §13.5:
    1. /go/<typ>/<ref>
    2. goto.php/<typ>/<ref>
    3. goto.php?target=<typ>_<ref>[_download]
    4. ilias.php?...ref_id=<ref> mit Typtabelle

    Returns (None, None) für leere Links, #, javascript:, etc.
    """
    if not href or href.strip() == "" or href == "#":
        return None, None

    href = href.strip()
    if href.startswith("#") or href.startswith("javascript:"):
        return None, None

    parsed = urlparse(href)
    path = parsed.path
    query = parsed.query

    # Form 1: /go/<typ>/<ref>
    typ, ref_id = _extract_from_go_path(path, base_url)
    if typ is not None and ref_id is not None:
        return typ, ref_id

    # Form 2: goto.php/<typ>/<ref>
    typ, ref_id = _extract_from_goto_path(path)
    if typ is not None and ref_id is not None:
        return typ, ref_id

    # Form 3: goto.php?target=<typ>_<ref>[_download]
    if path.endswith("/goto.php") or path == "/goto.php":
        typ, ref_id = _extract_from_goto_target(query)
        if typ is not None and ref_id is not None:
            return typ, ref_id

    # Form 4: ilias.php?...ref_id=<ref>
    if path.endswith("/ilias.php") or path == "/ilias.php":
        typ, ref_id = _extract_from_ilias_ref_id(query, base_url)
        if ref_id is not None:
            return typ, ref_id

    return None, None


def parse_link_with_icon_fallback(href: str, base_url: str, icon_alt: str | None = None) -> tuple[str, int | None]:
    """Parse Link mit Icon-Fallback für unbekannte Typen.

    Wenn der Link keinen Typ liefert, wird versucht, den Typ aus dem Icon-Alt-Text
    abzuleiten (z. B. 'Kurs' -> 'crs', 'Gruppe' -> 'grp').
    Unbekannte Typen geben 'other' zurück.
    """
    typ, ref_id = parse_link(href, base_url)
    if typ is not None:
        return typ, ref_id

    # Icon fallback
    if icon_alt:
        icon_lower = icon_alt.lower()
        icon_map = {
            "kurs": "crs",
            "gruppe": "grp",
            "ordner": "fold",
            "datei": "file",
            "weblink": "webr",
            "übung": "exc",
            "test": "tst",
            "forum": "frm",
            "wiki": "wiki",
            "sitzung": "sess",
            "kategorie": "cat",
        }
        for key, val in icon_map.items():
            if key in icon_lower:
                return val, ref_id

    return "other", ref_id