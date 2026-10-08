"""Parser für "Meine Kurse und Gruppen" (Spec §5.2/§13.2): reine Funktion, keine I/O.

`parse_memberships(html, base_url) -> list[Course]` parst ausschließlich den
Hauptinhalt (`#ilContentContainer .panel-body`) – Metabar-`il-item`s (z. B. die
Benachrichtigung mit Eigenschaft "Zeit") zählen nie als Kurse.
"""

from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup

from ..errors import ParserError
from ..models import Course
from .props import semester_from_period, semester_from_title

MAIN_SELECTORS = ("#ilContentContainer .panel-body", "#ilContentContainer", "div.panel-body")
ITEM_SELECTORS = ("li.il-std-item-container", "div.il-std-item", "div.il-item")
TITLE_LINK_SELECTORS = ("h4.il-item-title a", "h4 a", ".il-item-title a", "h4.il-item-title")
DESC_SELECTOR = "div.il-item-description"
PROP_NAME_SELECTOR = "span.il-item-property-name"
PROP_VALUE_SELECTOR = "span.il-item-property-value"
EMPTY_HINT_SELECTORS = (".alert-info", ".ilNoItems", ".il-empty-hint")

_GO_LINK = re.compile(r"/go/([a-zA-Z]+)/(\d+)")
_GOTO_LINK = re.compile(r"goto\.php/([a-zA-Z]+)/(\d+)")
_TARGET_LINK = re.compile(r"target=([a-zA-Z]+)_(\d+)")
_REF_ID_LINK = re.compile(r"ref_id=(\d+)")

_PERIOD_HINTS = ("zeitraum", "kurszeitraum", "period")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", html.unescape(text or ""))).strip()


def _ref_and_type(href: str) -> tuple[str | None, int | None]:
    m = _GO_LINK.search(href or "")
    if m:
        return m.group(1).lower(), int(m.group(2))
    m = _GOTO_LINK.search(href or "")
    if m:
        return m.group(1).lower(), int(m.group(2))
    m = _TARGET_LINK.search(href or "")
    if m:
        return m.group(1).lower(), int(m.group(2))
    m = _REF_ID_LINK.search(href or "")
    if m:
        return None, int(m.group(1))
    return None, None


def parse_memberships(html_text: str, base_url: str) -> list[Course]:
    """Kursliste aus ilmembershipoverviewgui parsen.

    - Leere Liste mit Leer-Hinweis (``.alert-info``) → ``[]`` (Exit 0, count 0).
    - Keine Liste und kein Leer-Hinweis (Wartungsseite/unerwartetes HTML) →
      :class:`ParserError` (Exit 5).
    """

    soup = BeautifulSoup(html_text or "", "html.parser")
    main = None
    for selector in MAIN_SELECTORS:
        main = soup.select_one(selector)
        if main is not None:
            break
    scope = main if main is not None else soup

    courses: list[Course] = []
    seen: set[int] = set()
    items = []
    for selector in ITEM_SELECTORS:
        items = scope.select(selector)
        if items:
            break

    for item in items:
        if item.find_parent(class_="il-maincontrols-metabar") is not None:
            # Metabar-Benachrichtigungen nie als Kurseinträge lesen
            continue
        link = None
        for selector in TITLE_LINK_SELECTORS:
            link = item.select_one(selector)
            if link is not None and link.name == "a":
                break
            if link is not None and link.find("a") is not None:
                link = link.find("a")
                break
        if link is None or link.name != "a":
            continue
        ref_type, ref_id = _ref_and_type(link.get("href", ""))
        if ref_id is None:
            continue
        if ref_type not in ("crs", "grp"):
            continue
        if ref_id in seen:
            continue
        seen.add(ref_id)

        fullname = _norm(link.get_text())
        if not fullname:
            continue
        desc_el = item.select_one(DESC_SELECTOR)
        description = _norm(desc_el.get_text()) if desc_el is not None else ""

        props: dict[str, str] = {}
        names = item.select(PROP_NAME_SELECTOR)
        values = item.select(PROP_VALUE_SELECTOR)
        for name_el, value_el in zip(names, values):
            props[_norm(name_el.get_text()).lower()] = _norm(value_el.get_text())

        visible = True
        if "status" in props and "offline" in props["status"].lower():
            visible = False

        semester: str | None = None
        for key, value in props.items():
            if any(hint in key for hint in _PERIOD_HINTS):
                semester = semester_from_period(value)
                if semester:
                    break
        if semester is None:
            semester = semester_from_title(fullname)

        courses.append(
            Course(
                id=ref_id,
                fullname=fullname,
                shortname="",
                category=None,
                semester=semester,
                visible=visible,
                startdate=None,
                enddate=None,
                url=f"{base_url.rstrip('/')}/go/{ref_type}/{ref_id}",
                course_type=ref_type,
                description=description,
            )
        )

    if courses:
        return courses

    for selector in EMPTY_HINT_SELECTORS:
        if scope.select_one(selector) is not None:
            return []

    raise ParserError(
        "Kursliste: weder Kurseinträge noch Leer-Hinweis gefunden (unerwartetes HTML)."
    )


def find_by_number(courses: list[Course], number: str) -> Course | None:
    """Spätere Kursnummern-Suche für `ls` (§13.1): exakter Titel-Treffer zuerst,
    dann Beschreibung. (S6: nur bereitstellen.)"""

    for c in courses:
        if number in c.fullname:
            return c
    for c in courses:
        if number in c.description:
            return c
    return None
