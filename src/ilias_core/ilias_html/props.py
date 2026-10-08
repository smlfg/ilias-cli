"""Eigenschafts-Parser für ILIAS: Semester, Größen, Datumsangaben.

Reine Funktionen (HTML-String -> Wert), keine I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass



# Deutsche Monatsabkürzungen
GERMAN_MONTHS = {
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


@dataclass(frozen=True)
class SizeResult:
    """Ergebnis der Größen-Parsing."""
    size: int | None          # Größe in Bytes
    size_text: str            # Originaltext (z. B. "203.45 KB")
    suffix: str | None = None # Dateiendung (z. B. "pdf")


def semester_from_title(title: str) -> str | None:
    """Extrahiere Semester aus einem Kurstitel.

    Erwartete Formen (Spec §5.3, §13):
    - WiSe 2026/27, WS 2026/27, WS26/27, Wintersemester 2026/27 -> "WiSe 2026/27"
    - SoSe 2026, SS 2026, SS26, Sommersemester 2026 -> "SoSe 2026"
    - WiSe26/27, _WS26_27, 2026 WS -> "WiSe 2026/27"
    - SoSe26, _SS26, 2026 SS -> "SoSe 2026"

    Eigenschaften wie "Anmeldungsende" oder "Freie Plätze" bestimmen das Semester NICHT.
    Fehlendes Semester -> None.
    """
    if not title:
        return None

    # Normalisieren: Entities werden vorher dekodiert, hier NFC und Whitespace
    text = unicodedata.normalize("NFC", title)
    text = re.sub(r"\s+", " ", text).strip()

    # Pattern 1: WiSe 2026/27, WS 2026/27, WS26/27, Wintersemester 2026/27
    # Auch: WiSe26/27 (ohne Leerzeichen), _WS26_27 (mit Unterstrichen), 2026 WS
    wise_patterns = [
        # WS26/27, WS26_27, WiSe26/27, _WS26_27
        r"(?:wi\s*se|ws|wintersemester)[\s_\-]*(\d{2,4})[\s_\-]*[/_-][\s_\-]*(\d{2,4})",
        # 2026 WS, 2026WS
        r"(?:^|[\s_\-])(\d{4})[\s_\-]*(?:ws|wi\s*se|wintersemester)(?:[\s_\-]|$)",
        # WiSe 2026
        r"(?:wi\s*se|ws|wintersemester)[\s_\-]*(\d{4})",
    ]
    for pattern in wise_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                # WiSe 26/27 oder 2026/27
                y1, y2 = groups
                y1 = _normalize_year(y1)
                y2 = _normalize_year(y2)
                if y1 and y2:
                    # Format: WiSe 2026/27 (zweites Jahr 2-stellig wenn möglich)
                    y1_int = int(y1)
                    y2_int = int(y2)
                    if y2_int == y1_int + 1:
                        return f"WiSe {y1_int}/{y2_int % 100:02d}"
                    return f"WiSe {y1}/{y2}"
            elif len(groups) == 1:
                # 2026 WS oder WiSe 2026
                y = _normalize_year(groups[0])
                if y:
                    y_int = int(y)
                    return f"WiSe {y_int}/{y_int % 100 + 1:02d}"

    # Pattern 2: SoSe 2026, SS 2026, SS26, Sommersemester 2026
    # Auch: SoSe26 (ohne Leerzeichen), _SS26 (mit Unterstrichen), 2026 SS
    sose_patterns = [
        r"(?:so\s*se|ss|sommersemester)[\s_\-]*(\d{2,4})",
        r"(?:^|[\s_\-])(\d{4})[\s_\-]*(?:ss|so\s*se|sommersemester)(?:[\s_\-]|$)",
    ]
    for pattern in sose_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            y = _normalize_year(m.group(1))
            if y:
                return f"SoSe {y}"

    return None


def _normalize_year(year_str: str) -> str | None:
    """Normalisiere Jahreszahl: 2-stellig -> 4-stellig (2000+), 4-stellig -> prüfen."""
    if not year_str.isdigit():
        return None
    if len(year_str) == 2:
        year = int(year_str)
        # 00-99 -> 2000-2099
        return f"{2000 + year:04d}"
    elif len(year_str) == 4:
        year = int(year_str)
        if 1900 <= year <= 2100:
            return year_str
    return None


def parse_size(size_text: str) -> SizeResult:
    """Parse eine Größenangabe wie '203.45 KB', '1,5 MB', '820 KB', '1 GB', '512 Bytes'.

    Akzeptiert Punkt und Komma als Dezimaltrenner. Basis 1024.
    Gibt SizeResult mit size (Bytes), size_text (Original), suffix (None) zurück.
    """
    if not size_text:
        return SizeResult(size=None, size_text="", suffix=None)

    original = size_text.strip()
    text = original.replace(",", ".")
    text = re.sub(r"[^\d\.]", " ", text)  # Nur Zahlen und Punkte behalten
    parts = text.split()
    if not parts:
        return SizeResult(size=None, size_text=original, suffix=None)

    try:
        value = float(parts[0])
    except ValueError:
        return SizeResult(size=None, size_text=original, suffix=None)

    # Einheit bestimmen (aus Originaltext)
    unit = ""
    unit_match = re.search(r"(KB|MB|GB|TB|BYTES?|B)\b", original, re.IGNORECASE)
    if unit_match:
        unit = unit_match.group(1).upper()

    multipliers = {
        "B": 1,
        "BYTES": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
    }

    multiplier = multipliers.get(unit, 1)
    size_bytes = int(value * multiplier)

    return SizeResult(size=size_bytes, size_text=original, suffix=None)


def parse_date_german(date_text: str) -> str | None:
    """Parse deutsches Datum wie '30. Dez 2025, 12:34' oder relative 'Heute, 12:34'.

    Returns ISO 8601 in Europe/Berlin oder None.
    """
    if not date_text:
        return None

    text = date_text.strip()

    # Relative Angaben: Heute, Gestern, Morgen
    from datetime import datetime, timedelta
    import zoneinfo

    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    now = datetime.now(tz)

    rel_match = re.match(r"^(heute|gestern|morgen)[,\s]+(\d{1,2}:\d{2})", text, re.IGNORECASE)
    if rel_match:
        day_word, time_str = rel_match.groups()
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            return None

        if day_word.lower() == "heute":
            target = now
        elif day_word.lower() == "gestern":
            target = now - timedelta(days=1)
        elif day_word.lower() == "morgen":
            target = now + timedelta(days=1)
        else:
            return None

        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target.isoformat()

    # Absolutes Datum: D. Mon YYYY, HH:MM (Tag ohne führende Null)
    abs_match = re.match(r"^(\d{1,2})\.\s*(\w{3,})\s+(\d{4})[,\s]+(\d{1,2}:\d{2})", text, re.IGNORECASE)
    if abs_match:
        day_str, month_str, year_str, time_str = abs_match.groups()
        try:
            day = int(day_str)
            year = int(year_str)
            month = GERMAN_MONTHS.get(month_str[:3].lower())
            if not month:
                return None
            hour, minute = map(int, time_str.split(":"))
            dt = datetime(year, month, day, hour, minute, tzinfo=tz)
            return dt.isoformat()
        except (ValueError, KeyError):
            return None

    return None


def extract_suffix(props: list[str]) -> str | None:
    """Extrahiere Dateiendung aus Eigenschaften (erste Eigenschaft, die wie eine Endung aussieht)."""
    for prop in props:
        prop = prop.strip().lower()
        # Typische Endungen: pdf, html, docx, etc.
        if re.match(r"^[a-z0-9]{1,5}$", prop) and prop not in {"kb", "mb", "gb", "bytes", "b"}:
            return prop
    return None