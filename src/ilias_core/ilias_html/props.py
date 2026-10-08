"""Reine Eigenschaften-Parser (Größen, Daten, Semester) für HHN-ILIAS-Seiten.

Keine I/O: HTML-Strings bzw. Roh-Texte rein, Werte raus. Einheitlich:
HTML-Entities dekodieren (Aufrufer), NFC-normalisieren, Whitespace normalisieren.

Semester-Regel (Spec §5.3, L9): März–August → SoSe des Jahres,
September–Dezember → WiSe Jahr/Jahr+1, Januar/Februar → WiSe Jahr-1/Jahr.
Fehlt das Semester, ist das der Normalfall bei der HHN → ``None`` (nie raten).
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["semester_from_title", "semester_from_period", "parse_german_date"]

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mär": 3,
    "mar": 3,
    "apr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "nov": 11,
    "dez": 12,
}


def _full_year(value: str) -> int:
    year = int(value)
    if year < 100:
        year += 2000
    return year


def _wise(start_year: int) -> str:
    return f"WiSe {start_year}/{str(start_year + 1)[-2:]}"


def _season(month: int, year: int) -> str:
    if 3 <= month <= 8:
        return f"SoSe {year}"
    if month >= 9:
        return _wise(year)
    return _wise(year - 1)


def semester_from_title(title: str | None) -> str | None:
    """Semester aus dem Kurstitel (Spec §5.3 + Live-Formen §13).

    Erkannt werden u. a. ``WiSe 2026/27``, ``WS 2026/27``, ``WS26/27``,
    ``WiSe26/27``, ``Wintersemester 2026/27``, ``_WS26_27``, ``2026 WS`` →
    ``WiSe 2026/27`` und ``SoSe 2026``, ``SS 2026``, ``SS26``, ``SoSe26``,
    ``Sommersemester 2026``, ``_SS26``, ``2026 SS`` → ``SoSe 2026``.
    Kein Treffer → ``None`` (wird nie geraten).
    """

    if not title:
        return None
    text = unicodedata.normalize("NFC", title)

    # SoSe zuerst: "SS" darf nicht als Teil von "SoSe"/"WS" matchen und
    # "WiSe"-Regex darf "SS"-Titel nicht greifen.
    m = re.search(r"(?<![A-Za-zÄÖÜäöüß])(?:Sommersemester|SoSe)\s*[ _\-]?\s*(\d{2,4})", text)
    if m:
        return f"SoSe {_full_year(m.group(1))}"
    m = re.search(r"(?<![A-Za-zÄÖÜäöüß0-9])SS\s*[ _\-]?\s*(\d{2,4})", text)
    if m:
        return f"SoSe {_full_year(m.group(1))}"
    m = re.search(r"(?<!\d)(\d{4})\s*[ _\-]?\s*(?:SS|SoSe)(?![A-Za-z])", text)
    if m:
        return f"SoSe {_full_year(m.group(1))}"

    m = re.search(r"(?<![A-Za-zÄÖÜäöüß])(?:Wintersemester|WiSe)\s*[ _\-]?\s*(\d{2,4})(?:\s*[/_\-]\s*(\d{2,4}))?", text)
    if m:
        # Ein- oder Zwei-Jahresform: "WS 2025/26" und "WiSe 2026" -> WiSe 2025/26 bzw. WiSe 2026/27
        return _wise(_full_year(m.group(1)))

    m = re.search(r"(?<![A-Za-zÄÖÜäöüß0-9])WS\s*[ _\-]?\s*(\d{2,4})(?:\s*[/_\-]\s*(\d{2,4}))?", text)
    if m:
        return _wise(_full_year(m.group(1)))

    m = re.search(r"(?<!\d)(\d{4})\s*[ _\-]?\s*(?:WS|WiSe)(?![A-Za-z])", text)
    if m:
        return _wise(_full_year(m.group(1)))

    return None


def parse_german_date(text: str) -> tuple[int, int, int] | None:
    """``16. Mär 2026`` -> ``(2026, 3, 16)`` (Tag ohne führende Null erlaubt)."""

    m = re.search(r"(\d{1,2})\.\s*([^\d\.\s]+)\.?\s+(\d{4})", text)
    if not m:
        return None
    month = _MONTHS.get(m.group(2).lower().rstrip("."))
    if month is None:
        return None
    return (int(m.group(3)), month, int(m.group(1)))


def semester_from_period(period: str | None) -> str | None:
    """Semester aus einer Zeitraum-Eigenschaft (``16. Mär 2026 - 31. Aug 2026``).

    Nur aus dem **Startdatum** abgeleitet (Spec §5.3); fehlt/unlesbar -> ``None``.
    """

    if not period:
        return None
    parsed = parse_german_date(period)
    if parsed is None:
        return None
    year, month, _day = parsed
    return _season(month, year)
