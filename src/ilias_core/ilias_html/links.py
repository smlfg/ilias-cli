"""Ein zentraler Link-/ref_id-Parser für alle ILIAS-Linkformen (Spec §13.5).

``parse_link(href, base_url) -> (typ | None, ref_id | None)`` in der Reihenfolge:

1. ``/go/<typ>/<ref>`` (HHN-Permalink)
2. ``goto.php/<typ>/<ref>``
3. ``goto.php?target=<typ>_<ref>[_download]``
4. ``ilias.php?…ref_id=<ref>`` mit fester Typtabelle

Die Groß-/Kleinschreibung der Query-Werte wird ignoriert. ``#``/leere Links
liefern ``(None, None)``. Unbekannte Typen geben ihr Kürzel zurück und werden
nie rekursiv geladen (das entscheidet der Aufrufer).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlsplit

_GO = re.compile(r"/go/([A-Za-z]+)/(\d+)")
_GOTO_PATH = re.compile(r"/goto\.php/([A-Za-z]+)/(\d+)")
_TARGET = re.compile(r"([A-Za-z]+)_(\d+)")

#: Merkmale im ``ilias.php``-Query -> Typ (Reihenfolge zählt).
_ILIAS_RULES: tuple[tuple[dict[str, str], str], ...] = (
    ({"cmdclass": "ilobjfilegui"}, "file"),
    ({"cmd": "sendfile"}, "file"),
    ({"baseclass": "illinkresourcehandlergui", "cmd": "calldirectlink"}, "webr"),
    ({"baseclass": "ilwikihandlergui"}, "wiki"),
    ({"baseclass": "ilexercisehandlergui"}, "exc"),
    ({"cmdclass": "ilobjtestgui"}, "tst"),
)


def _lowered_query(parts) -> dict[str, str]:
    return {key.lower(): (values[0].lower() if values else "") for key, values in parse_qs(parts.query).items()}


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def parse_link(href: str, base_url: str = "") -> tuple[str | None, int | None]:
    """Typ und ref_id aus einem ILIAS-Link lesen (nie eine Request auslösen)."""

    if not href:
        return (None, None)
    raw = href.strip()
    if not raw or raw.startswith("#"):
        return (None, None)

    parts = urlsplit(urljoin(base_url, raw))
    path = parts.path

    match = _GO.search(path)
    if match:
        return (match.group(1).lower(), int(match.group(2)))

    match = _GOTO_PATH.search(path)
    if match:
        return (match.group(1).lower(), int(match.group(2)))

    if path.endswith("goto.php"):
        target = (parse_qs(parts.query).get("target") or [""])[0]
        match = _TARGET.match(target)
        if match:
            return (match.group(1).lower(), int(match.group(2)))
        return (None, None)

    if path.endswith("ilias.php"):
        query = _lowered_query(parts)
        ref = _int_or_none(query.get("ref_id"))
        for markers, typ in _ILIAS_RULES:
            if all(query.get(key) == value for key, value in markers.items()):
                return (typ, ref)
        return (None, ref)

    return (None, None)
