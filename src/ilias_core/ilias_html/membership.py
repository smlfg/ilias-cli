"""Parser für "Meine Kurse und Gruppen" (S6, Spec §5.2/§13.2), rein und ohne I/O.

Quelle ist ausschließlich ``ilias.php?baseClass=ilmembershipoverviewgui``. Das
Dashboard (Favoriten-Teilmenge) wird nie geparst. Gelesen wird nur der
Hauptinhalt (``#ilContentContainer .panel-body``); der Metabar enthält ebenfalls
``.il-item`` (Benachrichtigungen mit der Eigenschaft "Zeit"), die nie als Kurs
oder Semester zählen dürfen.

Pro Eintrag wird **nur** der Titel-Link ``h4.il-item-title > a`` ausgewertet
(keine Dropdown-/Aktions-Links, ``href="#"`` wird ignoriert). Genau ein Eintrag
pro ref_id. ``id`` ist die ref_id aus dem Permalink ``/go/<typ>/<ref>``, nicht
die Kursnummer aus Titel/Beschreibung (Spec §13.1).
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ..errors import ParserError
from ..models import Course
from .links import parse_link
from .props import normalize_text, semester_from_properties, semester_from_title

PAGE_NAME = "Meine Kurse und Gruppen"

# Selektoren je mit Fallback (Spec §7), damit ein ILIAS-Update eine Stelle trifft.
CONTAINER_SELECTORS = ("#ilContentContainer",)
PANEL_SELECTORS = ("#ilContentContainer .panel-body", "#ilContentContainer .panel")
ITEM_SELECTORS = ("li.il-std-item-container", ".il-item.il-std-item", ".il-item")
TITLE_LINK_SELECTORS = (
    "h4.il-item-title a[href]",
    ".il-item-title a[href]",
    "a.il-item-title[href]",
)
DESCRIPTION_SELECTORS = (".il-item-description",)
PROPERTY_ROW_SELECTORS = (".il-multi-line-cap-3",)
EMPTY_HINT_SELECTORS = (".alert-info", ".ilNoItems")
_ICON_TYPE = re.compile(r"icon_([a-z]+)\.svg", re.IGNORECASE)
_MEMBERSHIP_TYPES = ("crs", "grp")


def parse_memberships(html: str, base_url: str) -> list[Course]:
    """Mitgliedschaften (Kurse und Gruppen) aus der ILIAS-Seite lesen.

    Rückgabe ist ungeordnet; die Sortierung übernimmt der Backend. Eine Seite
    ganz ohne Liste und Leer-Hinweis ist ein Parser-Fehler (Exit 5).
    """

    soup = BeautifulSoup(html, "html.parser")
    container = _first(soup, CONTAINER_SELECTORS)
    if container is None:
        raise _parse_error(base_url)

    panel = _first(container, PANEL_SELECTORS) or container
    items = _all(panel, ITEM_SELECTORS)

    if not items:
        if _first(panel, EMPTY_HINT_SELECTORS) is not None or _first(container, EMPTY_HINT_SELECTORS):
            return []
        raise _parse_error(base_url)

    courses: list[Course] = []
    seen: set[int] = set()
    for item in items:
        course = _course_from_item(item, base_url)
        if course is None or course.id in seen:
            continue
        seen.add(course.id)
        courses.append(course)

    if not courses:
        raise _parse_error(base_url)
    return courses


def _first(scope: Any, selectors: tuple[str, ...]) -> Any:
    for selector in selectors:
        found = scope.select_one(selector)
        if found is not None:
            return found
    return None


def _all(scope: Any, selectors: tuple[str, ...]) -> list[Any]:
    found = scope.select(selectors[0])
    if found:
        return found
    for selector in selectors[1:]:
        found = scope.select(selector)
        if found:
            return found
    return []


def _course_from_item(item: Any, base_url: str) -> Course | None:
    link = _first(item, TITLE_LINK_SELECTORS)
    if link is None:
        return None
    href = link.get("href") or ""
    typ, ref = parse_link(href, base_url)
    if typ not in _MEMBERSHIP_TYPES:
        typ = _type_from_icon(item) if typ is None else None
    if typ not in _MEMBERSHIP_TYPES or ref is None:
        return None

    title = normalize_text(link.get_text(" ", strip=True))
    properties = _properties(item)
    description = _description(item)
    return Course(
        id=ref,
        fullname=title,
        shortname="",
        category=None,
        semester=semester_from_title(title) or semester_from_properties(properties),
        visible=not _is_offline(properties),
        startdate=None,
        enddate=None,
        url=f"{base_url.rstrip('/')}/go/{typ}/{ref}",
        type=typ,
        description=description or None,
    )


def _properties(item: Any) -> dict[str, str]:
    properties: dict[str, str] = {}
    for row in _all(item, PROPERTY_ROW_SELECTORS):
        name_el = row.select_one(".il-item-property-name")
        value_el = row.select_one(".il-item-property-value")
        name = normalize_text(name_el.get_text(" ", strip=True)) if name_el else ""
        value = normalize_text(value_el.get_text(" ", strip=True)) if value_el else ""
        properties[name] = value
    return properties


def _is_offline(properties: dict[str, str]) -> bool:
    return any(value.strip().casefold() == "offline" for value in properties.values())


def _description(item: Any) -> str:
    node = _first(item, DESCRIPTION_SELECTORS)
    return normalize_text(node.get_text(" ", strip=True)) if node is not None else ""


def _type_from_icon(item: Any) -> str | None:
    image = item.select_one("img.icon") or item.select_one("img")
    if image is None:
        return None
    alt = (image.get("alt") or "").strip().casefold()
    if alt == "kurs":
        return "crs"
    if alt in ("gruppe", "gruppierung"):
        return "grp"
    match = _ICON_TYPE.search(image.get("src") or "")
    return match.group(1).lower() if match else None


def _parse_error(base_url: str) -> ParserError:
    base = base_url.rstrip("/")
    return ParserError(
        f'Unerwartete Seite für "{PAGE_NAME}" ({base}/ilias.php): '
        "weder Kursliste noch Leer-Hinweis gefunden.",
        hint="Die Seite sieht nicht wie die ILIAS-Mitgliedschaftsübersicht aus (ILIAS-Update?).",
    )
