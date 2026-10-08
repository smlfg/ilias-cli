"""Parser für die ILIAS-Mitgliedschafts-Übersicht (ilmembershipoverviewgui).

Spec §5.2, §13.2: Parse 'Meine Kurse und Gruppen' Seite.
Nur Hauptinhalt (#ilContentContainer .panel-body), keine Metabar-Benachrichtigungen.
"""

from __future__ import annotations

import html
import unicodedata

from bs4 import BeautifulSoup

from .links import parse_link
from .props import semester_from_title
from ..models import Course


# Selektoren für die Mitgliedschafts-Übersicht (ILIAS 9 UI)
# Spec §13.2: #ilContentContainer -> div.panel.panel-secondary.panel-flex -> div.panel-body
# -> div.il-item-group -> h3 (Kategorie) -> div.il-item-group-items > ul > li.il-std-item-container
# -> div.il-item.il-std-item -> div.media -> div.media-body -> h4.il-item-title > a

MEMBERSHIP_CONTAINER_SELECTOR = "#ilContentContainer .panel-body"
ITEM_GROUP_SELECTOR = "div.il-item-group"
ITEM_CONTAINER_SELECTOR = "li.il-std-item-container"
ITEM_SELECTOR = "div.il-item.il-std-item"
TITLE_LINK_SELECTOR = "h4.il-item-title > a"
DESCRIPTION_SELECTOR = "div.il-item-description"
PROPERTIES_SELECTOR = "div.row > div.col-md-6.il-multi-line-cap-3"
PROPERTY_NAME_SELECTOR = "span.il-item-property-name"
PROPERTY_VALUE_SELECTOR = "span.il-item-property-value"
OFFLINE_INDICATOR_SELECTOR = "span.il-item-property-value:contains('Offline')"


def _clean_text(text: str) -> str:
    """HTML-Entities dekodieren, NFC-normalisieren, Whitespace normalisieren, nie kürzen."""
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = " ".join(text.split())
    return text


def _extract_title_and_link(item_soup: BeautifulSoup, base_url: str) -> tuple[str, str, str | None, int | None]:
    """Extrahiere Titel, Link, Typ und ref_id aus einem Item.

    Returns: (title, url, type, ref_id)
    """
    link_elem = item_soup.select_one(TITLE_LINK_SELECTOR)
    if not link_elem:
        return "", "", None, None

    title = _clean_text(link_elem.get_text())
    href = link_elem.get("href", "")

    # Absolute URL bauen
    if href.startswith("/"):
        url = base_url.rstrip("/") + href
    elif href.startswith("http"):
        url = href
    else:
        url = base_url.rstrip("/") + "/" + href

    # Typ und ref_id aus Link extrahieren
    typ, ref_id = parse_link(href, base_url)

    return title, url, typ, ref_id


def _extract_description(item_soup: BeautifulSoup) -> str:
    """Extrahiere Beschreibungstext (für Kursnummern-Suche in ls)."""
    desc_elem = item_soup.select_one(DESCRIPTION_SELECTOR)
    if not desc_elem:
        return ""
    return _clean_text(desc_elem.get_text())


def _extract_properties(item_soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Extrahiere Eigenschaften (Name, Wert) aus dem Item."""
    props = []
    for prop_elem in item_soup.select(PROPERTIES_SELECTOR):
        name_elem = prop_elem.select_one(PROPERTY_NAME_SELECTOR)
        value_elem = prop_elem.select_one(PROPERTY_VALUE_SELECTOR)
        if name_elem and value_elem:
            name = _clean_text(name_elem.get_text())
            value = _clean_text(value_elem.get_text())
            props.append((name, value))
    return props


def _is_offline(props: list[tuple[str, str]]) -> bool:
    """Prüfe, ob ein Item als Offline markiert ist."""
    for name, value in props:
        if "offline" in value.lower() or "offline" in name.lower():
            return True
    return False


def _extract_semester_from_props(props: list[tuple[str, str]]) -> str | None:
    """Versuche Semester aus Eigenschaften zu extrahieren (Zeitraum/Kurszeitraum/Period).

    Spec §5.3: Eigenschaft 'Zeitraum'/'Kurszeitraum'/'Period' -> Startdatum -> SoSe März-Aug, WiSe Sep-Feb.
    """
    for name, value in props:
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in ["zeitraum", "kurszeitraum", "period"]):
            # Versuche Startdatum zu extrahieren (erstes Datum in Wert)
            from .props import parse_date_german
            # Einfaches Suchen nach Datumsmuster
            import re
            date_match = re.search(r"(\d{1,2}\.\s*\w{3,}\s+\d{4})", value)
            if date_match:
                date_str = date_match.group(1)
                parsed = parse_date_german(date_str + ", 00:00")
                if parsed:
                    # Monat bestimmen
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
                        month = dt.month
                        year = dt.year
                        if 3 <= month <= 8:
                            return f"SoSe {year}"
                        else:
                            if month <= 2:
                                year -= 1
                            return f"WiSe {year}/{year+1}"
                    except ValueError:
                        pass
    return None


def parse_memberships(html: str, base_url: str) -> list[Course]:
    """Parse die HTML-Seite 'Meine Kurse und Gruppen' (ilmembershipoverviewgui).

    Args:
        html: Vollständiger HTML-Inhalt der Seite
        base_url: Basis-URL der ILIAS-Instanz (z. B. https://ilias.hs-heilbronn.de)

    Returns:
        Liste von Course-Objekten mit id=ref_id, type, fullname, shortname="",
        semester, visible, url, startdate/enddate/category=None.

    Spec §5.2, §13.2:
    - Nur Hauptinhalt (#ilContentContainer .panel-body)
    - Keine Metabar-Benachrichtigungen (haben auch .il-item mit Eigenschaft 'Zeit')
    - Ein Eintrag pro ref_id (Titel nur aus a.il_ContainerItemTitle, aber hier h4.il-item-title > a)
    - Typ aus Link (crs/grp), nicht aus Icon
    - Offline -> visible=False
    - Semester aus Titel (Priorität) oder Eigenschaften (Zeitraum)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Hauptinhalt finden (nur #ilContentContainer .panel-body, nicht Metabar)
    container = soup.select_one(MEMBERSHIP_CONTAINER_SELECTOR)
    if not container:
        return []

    courses = []
    seen_ref_ids = set()

    # Alle Item-Gruppen durchlaufen (Kategorien/Orte)
    for group in container.select(ITEM_GROUP_SELECTOR):
        # Items in dieser Gruppe
        for item_container in group.select(ITEM_CONTAINER_SELECTOR):
            item = item_container.select_one(ITEM_SELECTOR)
            if not item:
                continue

            # Titel, Link, Typ, ref_id extrahieren
            title, url, typ, ref_id = _extract_title_and_link(item, base_url)
            if not title or ref_id is None or typ not in ("crs", "grp"):
                continue

            # Duplikate vermeiden (ein Eintrag pro ref_id)
            if ref_id in seen_ref_ids:
                continue
            seen_ref_ids.add(ref_id)

            # Beschreibung extrahieren (für spätere Kursnummer-Suche in ls)
            description = _extract_description(item)

            # Eigenschaften extrahieren
            props = _extract_properties(item)

            # Offline-Prüfung
            offline = _is_offline(props)
            visible = not offline

            # Semester bestimmen: erst aus Titel, dann aus Eigenschaften (Zeitraum)
            semester = semester_from_title(title)
            if semester is None:
                semester = _extract_semester_from_props(props)

            # Course-Objekt erstellen
            course = Course(
                id=ref_id,
                fullname=title,
                shortname="",
                category=None,
                semester=semester,
                visible=visible,
                startdate=None,
                enddate=None,
                url=url,
                type=typ,
                description=description,
            )
            courses.append(course)

    return courses


def has_empty_membership_hint(html: str) -> bool:
    """Prüfe, ob die Seite einen Leer-Hinweis enthält (Spec §5.2).

    Leere Liste: .alert-info mit Text 'Sie sind noch keinem Kurs und keiner Gruppe beigetreten.'
    """
    soup = BeautifulSoup(html, "html.parser")
    alert = soup.select_one(".alert-info")
    if not alert:
        return False
    text = _clean_text(alert.get_text()).lower()
    return "keinem kurs" in text and "keiner gruppe" in text


def has_login_marker(html: str) -> bool:
    """Prüfe, ob die Seite ein Login-Merkmal hat (Metabar mit login.php statt logout.php)."""
    soup = BeautifulSoup(html, "html.parser")
    metabar = soup.select_one(".il-maincontrols-metabar")
    if not metabar:
        return False
    # Nach login.php Link suchen
    login_link = metabar.select_one('a[href*="login.php"]')
    logout_link = metabar.select_one('a[href*="logout.php"]')
    return login_link is not None and logout_link is None