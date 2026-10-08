"""Reine Funktionen für Semester-, Datums- und Textableitung (kein I/O).

Semester (Spec §5.3/§13): Das Semester steht an der HHN nur im Titel. Etwa die
Hälfte der echten Titel enthält gar keins – ``None`` ist dort der Normalfall,
es wird nie geraten. Eigenschaften wie "Anmeldungsende" oder "Freie Plätze"
bestimmen das Semester **nicht**; nur ein Zeitraum ("Zeitraum"/"Kurszeitraum"/
"Period") darf als Ersatz dienen (Startdatum -> Regel L9).

Erkannte Titelformen (jeweils -> ``WiSe 2026/27`` bzw. ``SoSe 2026``):
``WiSe 2026/27`` · ``WS 2026/27`` · ``WS26/27`` · ``WiSe26/27`` ·
``Wintersemester 2026/27`` · ``_WS26_27`` · ``2026 WS`` · ``SoSe 2026`` ·
``SS 2026`` · ``SS26`` · ``SoSe26`` · ``Sommersemester 2026`` · ``_SS26`` ·
``2026 SS``.
"""

from __future__ import annotations

import html
import re
import unicodedata

from ..timeutil import semester_from_month

# Wortgrenze: davor darf kein Buchstabe stehen (Unterstrich/Zahl sind erlaubt,
# damit ``_WS26_27`` erkannt wird). Bewusst ohne ``\b``, weil ``_`` ein
# Wortzeichen ist.
_NOT_LETTER = r"(?<![A-Za-zÄÖÜäöüß])"
_WINTER = r"(?:Wintersemester|WiSe|WS)"
_SUMMER = r"(?:Sommersemester|SoSe|SS)"
_SEP = r"[\s_\-./]*"

# Reihenfolge zählt: erst der vollständige Bereich (WiSe 2026/27, _WS26_27),
# dann Einzeljahr, Kurzform und "Jahr zuerst" (2026 WS).
_WINTER_RANGE = re.compile(_NOT_LETTER + _WINTER + _SEP + r"(\d{2,4})[\s_\-./]+(\d{2,4})")
_WINTER_SINGLE = re.compile(_NOT_LETTER + _WINTER + _SEP + r"(\d{4})")
_WINTER_SHORT = re.compile(_NOT_LETTER + _WINTER + _SEP + r"(\d{2})(?!\d)")
_WINTER_FIRST = re.compile(r"(?<!\d)(\d{4})(?!\d)" + _SEP + _WINTER)
_SUMMER_SINGLE = re.compile(_NOT_LETTER + _SUMMER + _SEP + r"(\d{4})")
_SUMMER_SHORT = re.compile(_NOT_LETTER + _SUMMER + _SEP + r"(\d{2})(?!\d)")
_SUMMER_FIRST = re.compile(r"(?<!\d)(\d{4})(?!\d)" + _SEP + _SUMMER)

# Deutsche Monatskürzel der ILIAS-Oberfläche (22.10.2026 -> Okt).
_MONTHS = {
    "jan": 1, "feb": 2, "mär": 3, "mrz": 3, "maer": 3, "apr": 4, "mai": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11,
    "dez": 12,
}
_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]{3,})\.?\s+(\d{4})"
)
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """HTML-Entities dekodieren, NFC-normalisieren, Leerraum normalisieren.

    Es wird nie gekürzt (Spec §6.3/§13.9).
    """

    if not text:
        return ""
    decoded = html.unescape(text)
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", decoded)).strip()


def _winter(year: int) -> str:
    return f"WiSe {year}/{str(year + 1)[-2:]}"


def _summer(year: int) -> str:
    return f"SoSe {year}"


def _year(value: str) -> int:
    number = int(value)
    return 2000 + number if len(value) == 2 else number


def semester_from_title(title: str) -> str | None:
    """Semester aus dem Titel ableiten; kein erkennbares Muster -> ``None``."""

    if not title:
        return None
    text = unicodedata.normalize("NFC", title)
    match = _WINTER_RANGE.search(text)
    if match:
        return _winter(_year(match.group(1)))
    match = _SUMMER_SINGLE.search(text)
    if match:
        return _summer(_year(match.group(1)))
    match = _WINTER_SINGLE.search(text)
    if match:
        return _winter(_year(match.group(1)))
    match = _WINTER_SHORT.search(text)
    if match:
        return _winter(_year(match.group(1)))
    match = _SUMMER_SHORT.search(text)
    if match:
        return _summer(_year(match.group(1)))
    match = _WINTER_FIRST.search(text)
    if match:
        return _winter(int(match.group(1)))
    match = _SUMMER_FIRST.search(text)
    if match:
        return _summer(int(match.group(1)))
    return None


def _month_number(name: str) -> int | None:
    key = name.lower().rstrip(".")
    return _MONTHS.get(key) or _MONTHS.get(key[:3])


def semester_from_period(text: str) -> str | None:
    """Semester aus einem Zeitraum-Text (Startdatum) ableiten (Regel L9, §5.3).

    ``16. Mär 2026 - 31. Aug 2026`` -> ``SoSe 2026``. Ohne erkennbares
    Startdatum -> ``None``.
    """

    if not text:
        return None
    match = _DATE.search(unicodedata.normalize("NFC", text))
    if match is None:
        return None
    month = _month_number(match.group(2))
    if month is None:
        return None
    return semester_from_month(int(match.group(3)), month)


#: Eigenschaftsnamen, die einen Veranstaltungszeitraum tragen (Spec §5.3).
PERIOD_PROPERTY_NAMES = ("zeitraum", "kurszeitraum", "period")


def semester_from_properties(properties: dict[str, str]) -> str | None:
    """Semester aus den Item-Eigenschaften: nur ein Zeitraum zählt, nie "Anmeldungsende"."""

    for name, value in properties.items():
        if name.strip().casefold() in PERIOD_PROPERTY_NAMES:
            semester = semester_from_period(value)
            if semester:
                return semester
    return None
