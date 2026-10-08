"""Link-Parser für ILIAS-Seiten: Typ und ref_id aus HREF bestimmen (Spec §13.5).

Pure Funktionen (HTML-String + base_url -> Dataclasses/Dicts), kein I/O.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, parse_qs

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Tuple

# Typ-Tabelle für ilias.php?...ref_id= Links (Spec §13.5)
# Reihenfolge ist wichtig: spezifischere Merkmale zuerst
TYPE_TABLE: list[tuple[str, str]] = [
    (r"cmdClass=ilObjFileGUI", "file"),
    (r"cmd=sendfile", "file"),
    (r"baseClass=ilLinkResourceHandlerGUI.*cmd=calldirectlink", "webr"),
    (r"baseClass=ilWikiHandlerGUI", "wiki"),
    (r"baseClass=ilExerciseHandlerGUI", "exc"),
    (r"cmdClass=ilobjtestgui", "tst"),
    (r"baseClass=ilrepositorygui", None),  # Typ nur über Icon bestimmbar
]

# Pattern für /go/<typ>/<ref>
GO_PATTERN = re.compile(r"/go/([a-z]+)/(\d+)", re.IGNORECASE)
# Pattern für goto.php/<typ>/<ref>
GOTO_PATH_PATTERN = re.compile(r"goto\.php/([a-z]+)/(\d+)", re.IGNORECASE)
# Pattern für goto.php?target=<typ>_<ref>[_download]
GOTO_QUERY_PATTERN = re.compile(r"target=([a-z]+)_(\d+)(?:_download)?", re.IGNORECASE)


def parse_link(href: str, base_url: str) -> tuple[str | None, int | None]:
    """Typ und ref_id aus einem ILIAS-Link extrahieren (Spec §13.5).

    Reihenfolge:
    1. /go/<typ>/<ref> (HHN-Permalink)
    2. goto.php/<typ>/<ref>
    3. goto.php?target=<typ>_<ref>[_download]
    4. ilias.php?...ref_id=<ref> mit Typtabelle
    5. #/leer -> (None, None)

    Args:
        href: Der Link (kann relativ oder absolut sein)
        base_url: Basis-URL der ILIAS-Instanz (für relative Links)

    Returns:
        Tuple (typ, ref_id) oder (None, None) falls nicht bestimmbar
    """
    if not href or href.strip() == "#":
        return None, None

    href = href.strip()

    # Absolute URL bauen falls relativ
    if not href.startswith(("http://", "https://")):
        href = urljoin(base_url, href)

    parsed = urlparse(href)
    path = parsed.path
    query = parsed.query

    # 1. /go/<typ>/<ref>
    m = GO_PATTERN.search(path)
    if m:
        typ = m.group(1).lower()
        ref = int(m.group(2))
        return typ, ref

    # 2. goto.php/<typ>/<ref>
    m = GOTO_PATH_PATTERN.search(path)
    if m:
        typ = m.group(1).lower()
        ref = int(m.group(2))
        return typ, ref

    # 3. goto.php?target=<typ>_<ref>[_download]
    m = GOTO_QUERY_PATTERN.search(query)
    if m:
        typ = m.group(1).lower()
        ref = int(m.group(2))
        return typ, ref

    # 4. ilias.php?...ref_id=<ref> mit Typtabelle
    if "ilias.php" in path.lower() or "ilias.php" in query.lower():
        qs = parse_qs(query, keep_blank_values=True)
        # Case-insensitive lookup for ref_id
        ref_id_str = ""
        for key, values in qs.items():
            if key.lower() == "ref_id":
                ref_id_str = values[0]
                break
        if ref_id_str.isdigit():
            ref_id = int(ref_id_str)
            # Typtabelle abarbeiten (case-insensitive Query-Werte)
            full_query_lower = query.lower()
            for pattern, typ in TYPE_TABLE:
                if re.search(pattern, full_query_lower, re.IGNORECASE):
                    return typ, ref_id
            # Kein Typ in Tabelle gefunden -> None (Typ nur über Icon bestimmbar)
            return None, ref_id

    return None, None


def parse_link_from_item(item_el, base_url: str) -> tuple[str | None, int | None]:
    """Typ und ref_id aus einem Container-List-Item extrahieren.

    Verwendet data-list-item-id als primäre Quelle für ref_id (zuverlässig für alle Typen),
    und den Titel-Link für den Typ.

    Args:
        item_el: BeautifulSoup Element des .ilContainerListItemOuter
        base_url: Basis-URL der ILIAS-Instanz

    Returns:
        Tuple (typ, ref_id)
    """
    # ref_id aus data-list-item-id (Format: lg_div_<ref>_pref_<parent>)
    data_id = item_el.get("data-list-item-id", "")
    ref_id = None
    if data_id:
        # Format: lg_div_900201_pref_900101
        parts = data_id.split("_")
        for i, part in enumerate(parts):
            if part.isdigit() and (i == 0 or parts[i-1] in ("div", "pref")):
                ref_id = int(part)
                break

    # Typ aus dem Titel-Link
    title_link = item_el.select_one("a.il_ContainerItemTitle")
    typ = None
    if title_link and title_link.get("href"):
        typ, link_ref_id = parse_link(title_link["href"], base_url)
        # ref_id aus data-list-item-id ist zuverlässiger
        if ref_id is None:
            ref_id = link_ref_id

    return typ, ref_id