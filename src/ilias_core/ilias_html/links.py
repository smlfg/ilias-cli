"""Link-Parser für ILIAS-HTML-Seiten (Spec §13.5).

Bestimmt Typ und ref_id aus verschiedenen ILIAS-Link-Mustern.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlsplit


def _normalize_path(href: str) -> str:
    """Normalisiere einen href-Wert zu einem lowercase-Pfad/Query-Kombination.

    Verarbeitet sowohl vollständige URLs (mit Schema) als auch relative Pfade.
    Das Ergebnis ist ein zusammenhängender lowercase-String, in dem gesucht werden kann.
    """
    parsed = urlsplit(href)
    if parsed.scheme:
        # Vollständige URL: Pfad und Query zu einem String kombinieren
        if parsed.query:
            return (parsed.path + "?" + parsed.query).lower()
        return parsed.path.lower()
    else:
        # Relativer Pfad (ohne Schema) - ganze Zeichenkette lowercase
        return href.lower()


def parse_link(href: str, base_url: str) -> tuple[Optional[str], Optional[int]]:
    """Parst einen ILIAS-Link und gibt (typ, ref_id) zurück.

    Typen gemäß Spec §13.5 Typtabelle:
    - crs: /go/crs/<ref>
    - fold: /go/fold/<ref> oder goto.php/fold/<ref>
    - grp: goto.php?target=grp_<ref>
    - file: goto.php?target=file_<ref>_download
          oder ilias.php?...cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=<ref>
    - webr: ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=<ref>&cmd=calldirectlink
    - wiki: ilias.php?baseClass=ilWikiHandlerGUI&ref_id=<ref>
    - exc: ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=<ref>
    - tst: ilias.php?baseClass=ilobjtestgui&ref_id=<ref>
    - course_link: /go/crs/<ref> (auch als Permalink)
    - sonst None (Typ nur über Icon bestimmbar)

    Rückgabe: (typ, ref_id) oder (None, None) bzw. (None, ref_id) wenn Typ unsicher ist.
    """

    if not href:
        return (None, None)

    path = _normalize_path(href)

    # 1. /go/<typ>/<ref> (HHN-Permalink, live für crs, grp, fold, exc, cat, root)
    m = re.search(r"/go/([a-z]+)/(\d+)", path)
    if m:
        typ = m.group(1)
        ref_id = int(m.group(2))
        return (typ, ref_id)

    # 2. goto.php/<typ>/<ref>
    m = re.search(r"goto\.php/([a-z]+)/(\d+)", path)
    if m:
        typ = m.group(1)
        ref_id = int(m.group(2))
        return (typ, ref_id)

    # 3. goto.php?target=<typ>_<ref>[_download]
    m = re.search(
        r"goto\.php\?(?:.*&*)?target=([a-z_]+)_?(\d+)(?:_download)?(?:.*)?",
        path,
    )
    if m:
        typ = m.group(1).replace("_", "")
        ref_id = int(m.group(2))
        return (typ, ref_id)

    # 4. ilias.php?...ref_id=<ref> mit Typtabelle
    # cmdClass=ilObjFileGUI oder cmd=sendfile -> file
    if re.search(r"cmdclass=ilobjfilegui", path) or re.search(r"cmd=sendfile", path):
        m = re.search(r"ref_id=(\d+)", path)
        if m:
            ref_id = int(m.group(1))
            return ("file", ref_id)

    # baseClass=ilLinkResourceHandlerGUI + cmd=calldirectlink -> webr
    # Hinweis: lowercased -> illinkresourcehandlergui (kein extra "er" zwischen link und resource)
    if re.search(r"baseclass=illinkresourcehandlergui", path) and re.search(
        r"cmd=calldirectlink", path
    ):
        m = re.search(r"ref_id=(\d+)", path)
        if m:
            ref_id = int(m.group(1))
            return ("webr", ref_id)

    # baseClass=ilWikiHandlerGUI -> wiki
    if re.search(r"baseclass=ilwikihandlergui", path):
        m = re.search(r"ref_id=(\d+)", path)
        if m:
            ref_id = int(m.group(1))
            return ("wiki", ref_id)

    # baseClass=ilExerciseHandlerGUI -> exc
    if re.search(r"baseclass=ilexercisehandlergui", path):
        m = re.search(r"ref_id=(\d+)", path)
        if m:
            ref_id = int(m.group(1))
            return ("exc", ref_id)

    # baseClass=ilobjtestgui -> tst
    if re.search(r"baseclass=ilobjtestgui", path):
        m = re.search(r"ref_id=(\d+)", path)
        if m:
            ref_id = int(m.group(1))
            return ("tst", ref_id)

    # ilias.php?...ref_id=<ref> ohne weitere Merkmal -> Typ unsicher (None, ref_id)
    m = re.search(r"ref_id=(\d+)", path)
    if m:
        ref_id = int(m.group(1))
        return (None, ref_id)

    # Leerer Link oder nur #
    if path == "#" or not path.strip():
        return (None, None)

    # Unbekannter Typ
    return (None, None)
