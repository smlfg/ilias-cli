"""Parser für 'Meine Kurse und Gruppen' (ilmembershipoverviewgui) (Spec §5, §13.2).

Pure Funktionen, kein I/O. Nur Hauptinhalt (#ilContentContainer .panel-body) parsen.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from .links import parse_link

if TYPE_CHECKING:
    from typing import List, Optional


@dataclass(frozen=True)
class Membership:
    """Eine Mitgliedschaft (Kurs oder Gruppe) aus der Übersicht."""
    ref_id: int
    type: str  # "crs" oder "grp"
    title: str
    description: str
    visible: bool
    semester: str | None
    url: str


# Selektoren (mit Fallbacks)
PANEL_BODY_SELECTOR = "#ilContentContainer .panel-body"
ITEM_GROUP_SELECTOR = ".il-item-group"
ITEM_CONTAINER_SELECTOR = ".il-std-item-container"
ITEM_SELECTOR = ".il-item.il-std-item"
TITLE_LINK_SELECTOR = "h4.il-item-title a"
DESCRIPTION_SELECTOR = ".il-item-description"
PROPS_ROW_SELECTOR = ".il-item-properties .col-md-6.il-multi-line-cap-3"
PROP_NAME_SELECTOR = ".il-item-property-name"
PROP_VALUE_SELECTOR = ".il-item-property-value"
OFFLINE_SELECTOR = ".il-item-property-value:contains('Offline')"  # wird per Text geprüft
ICON_SELECTOR = ".media-left img.icon"


# Semester-Patterns (Spec §5.3, §13.11)
SEMESTER_PATTERNS = [
    # (regex, normalisierter Name) - Reihenfolge wichtig: spezifischere zuerst
    # WiSe mit 4-stelligen Jahren: WiSe 2026/27, WS 2025/26 (zweites Jahr 2 oder 4-stellig)
    (re.compile(r"\bWiSe\s*(\d{4})[/\-](\d{2,4})\b", re.IGNORECASE), lambda m: f"WiSe {m.group(1)}/{m.group(2)[-2:]}"),
    (re.compile(r"\bWS\s*(\d{4})[/\-](\d{2,4})\b", re.IGNORECASE), lambda m: f"WiSe {m.group(1)}/{m.group(2)[-2:]}"),
    (re.compile(r"\bWintersemester\s+(\d{4})[/\-](\d{2,4})\b", re.IGNORECASE), lambda m: f"WiSe {m.group(1)}/{m.group(2)[-2:]}"),
    # WiSe mit 2-stelligen Jahren: WiSe26/27 -> WiSe 2026/27, _WS26_27 -> WiSe 2026/27
    (re.compile(r"\bWiSe(\d{2})[/_](\d{2})\b", re.IGNORECASE), lambda m: f"WiSe 20{m.group(1)}/{m.group(2)}"),
    (re.compile(r"\b_WS(\d{2})_(\d{2})\b", re.IGNORECASE), lambda m: f"WiSe 20{m.group(1)}/{m.group(2)}"),
    # 2026 WS / Test 2026 WS -> WiSe 2026/27
    (re.compile(r"\b(\d{4})\s*WS\b", re.IGNORECASE), lambda m: f"WiSe {m.group(1)}/{str(int(m.group(1))+1)[-2:]}"),
    # SoSe mit 4-stelligen Jahren: SoSe 2026
    (re.compile(r"\bSoSe\s*(\d{4})\b", re.IGNORECASE), "SoSe {0}"),
    (re.compile(r"\bSS\s*(\d{4})\b", re.IGNORECASE), "SoSe {0}"),
    (re.compile(r"\bSommersemester\s+(\d{4})\b", re.IGNORECASE), "SoSe {0}"),
    # SoSe mit 2-stelligen Jahren: SoSe26, SS26, _SS26
    (re.compile(r"\bSoSe(\d{2})\b", re.IGNORECASE), lambda m: f"SoSe 20{m.group(1)}"),
    (re.compile(r"\bSS(\d{2})\b", re.IGNORECASE), lambda m: f"SoSe 20{m.group(1)}"),
    (re.compile(r"\b_SS(\d{2})\b", re.IGNORECASE), lambda m: f"SoSe 20{m.group(1)}"),
    # 2026 SS -> SoSe 2026
    (re.compile(r"\b(\d{4})\s*SS\b", re.IGNORECASE), lambda m: f"SoSe {m.group(1)}"),
]

# Zeitraum-Eigenschaft: "16. Mär 2026 - 31. Aug 2026"
PERIOD_PATTERN = re.compile(
    r"(\d{1,2})\.\s*([A-Za-zÄÖÜ]{3})\s*(\d{4})\s*[-–]\s*(\d{1,2})\.\s*([A-Za-zÄÖÜ]{3})\s*(\d{4})",
    re.IGNORECASE
)

GERMAN_MONTHS = {
    "Jan": 1, "Feb": 2, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12,
}


def normalize_text(text: str) -> str:
    """HTML-Entities dekodieren, NFC normalisieren, Whitespace normalisieren."""
    if not text:
        return ""
    # BeautifulSoup hat Entities schon dekodiert, aber sicherheitshalber
    text = text.replace("&nbsp;", " ").replace("&", "&").replace("<", "<").replace(">", ">")
    text = unicodedata.normalize("NFC", text)
    # Whitespace normalisieren: multiple spaces/newlines -> single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_semester_from_period(period_text: str) -> str | None:
    """Semester aus Zeitraum-Eigenschaft ableiten (Startdatum: März-August = SoSe, Sep-Feb = WiSe)."""
    m = PERIOD_PATTERN.search(period_text)
    if not m:
        return None
    start_month_str = m.group(2)
    start_year = int(m.group(3))
    start_month = GERMAN_MONTHS.get(start_month_str)
    if start_month is None:
        return None
    if 3 <= start_month <= 8:
        return f"SoSe {start_year}"
    else:
        # Sep-Feb -> WiSe Jahr/Jahr+1 (Jan/Feb gehören zum WiSe des Vorjahres)
        # Format: WiSe 2026/27 (2-stelliges zweites Jahr)
        if start_month <= 2:
            return f"WiSe {start_year-1}/{str(start_year)[-2:]}"
        return f"WiSe {start_year}/{str(start_year+1)[-2:]}"


def extract_semester_from_title(title: str) -> str | None:
    """Semester aus Titel per Pattern-Matching extrahieren (Spec §5.3, §13.11)."""
    for pattern, template in SEMESTER_PATTERNS:
        m = pattern.search(title)
        if m:
            if callable(template):
                return template(m)
            groups = m.groups()
            if len(groups) == 2:
                return template.format(groups[0], groups[1])
            elif len(groups) == 1:
                return template.format(groups[0])
    return None


def parse_semester(item_el, title: str) -> str | None:
    """Semester bestimmen: erst Zeitraum-Eigenschaft, dann Titel."""
    # Zeitraum-Eigenschaft suchen
    for prop_row in item_el.select(PROPS_ROW_SELECTOR):
        name_el = prop_row.select_one(PROP_NAME_SELECTOR)
        value_el = prop_row.select_one(PROP_VALUE_SELECTOR)
        if name_el and value_el:
            name = normalize_text(name_el.get_text())
            value = normalize_text(value_el.get_text())
            if name.lower() in ("zeitraum", "kurszeitraum", "period"):
                sem = extract_semester_from_period(value)
                if sem:
                    return sem
    # Fallback: Titel
    return extract_semester_from_title(title)


def parse_memberships(html: str, base_url: str) -> list[Membership]:
    """Mitgliedschaften aus 'Meine Kurse und Gruppen' parsen (Spec §13.2).

    Args:
        html: Vollständiges HTML der Seite
        base_url: Basis-URL der ILIAS-Instanz

    Returns:
        Liste von Membership-Objekten
    """
    soup = BeautifulSoup(html, "html.parser")

    # Nur Hauptinhalt parsen (nicht Metabar-Benachrichtigungen)
    panel_body = soup.select_one(PANEL_BODY_SELECTOR)
    if not panel_body:
        return []

    memberships = []

    for item_group in panel_body.select(ITEM_GROUP_SELECTOR):
        for container in item_group.select(ITEM_CONTAINER_SELECTOR):
            item = container.select_one(ITEM_SELECTOR)
            if not item:
                continue

            # Titel-Link
            title_link = item.select_one(TITLE_LINK_SELECTOR)
            if not title_link or not title_link.get("href"):
                continue

            title = normalize_text(title_link.get_text())
            href = title_link["href"]

            # Typ und ref_id aus Link
            typ, ref_id = parse_link(href, base_url)
            if typ not in ("crs", "grp") or ref_id is None:
                # Fallback: Icon
                icon = item.select_one(ICON_SELECTOR)
                if icon and icon.get("alt"):
                    alt = icon["alt"].lower()
                    if "kurs" in alt:
                        typ = "crs"
                    elif "gruppe" in alt:
                        typ = "grp"
                # ref_id aus href nochmal versuchen
                if ref_id is None:
                    _, ref_id = parse_link(href, base_url)

            if typ not in ("crs", "grp") or ref_id is None:
                continue

            # Beschreibung
            desc_el = item.select_one(DESCRIPTION_SELECTOR)
            description = normalize_text(desc_el.get_text()) if desc_el else ""

            # Eigenschaften (für Semester und Offline)
            props = []
            offline = False
            for prop_row in item.select(PROPS_ROW_SELECTOR):
                name_el = prop_row.select_one(PROP_NAME_SELECTOR)
                value_el = prop_row.select_one(PROP_VALUE_SELECTOR)
                if name_el and value_el:
                    name = normalize_text(name_el.get_text())
                    value = normalize_text(value_el.get_text())
                    props.append((name, value))
                    if value.lower() == "offline":
                        offline = True

            # Semester bestimmen
            semester = parse_semester(item, title)

            # URL: kanonischer Permalink
            url = f"{base_url.rstrip('/')}/go/{typ}/{ref_id}"

            memberships.append(Membership(
                ref_id=ref_id,
                type=typ,
                title=title,
                description=description,
                visible=not offline,
                semester=semester,
                url=url,
            ))

    return memberships