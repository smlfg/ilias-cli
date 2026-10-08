"""Parser für Datei-Eigenschaften: Größe, Datum, Endung (Spec §6.4, §13.4).

Pure Funktionen, kein I/O.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

# Deutsche Monatsabkürzungen
GERMAN_MONTHS = {
    "Jan": 1, "Feb": 2, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12,
}

# Größe: Zahl mit Punkt oder Komma + Einheit (KB, MB, GB, Bytes)
SIZE_PATTERN = re.compile(
    r"^\s*([\d.,]+)\s*(KB|MB|GB|Bytes?)\s*$", re.IGNORECASE
)

# Datum: D. Mon YYYY, HH:MM (z. B. "25. Sep 2026, 10:12")
DATE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\.\s*([A-Za-zÄÖÜ]{3})\s*(\d{4}),\s*(\d{1,2}):(\d{2})\s*$"
)

# Relative Datumsangaben: Heute/Gestern/Morgen, HH:MM
RELATIVE_DATE_PATTERN = re.compile(
    r"^\s*(Heute|Gestern|Morgen),\s*(\d{1,2}):(\d{2})\s*$", re.IGNORECASE
)


def parse_size(text: str) -> int | None:
    """Größe in Bytes parsen (Punkt und Komma als Dezimaltrenner, Basis 1024).

    Args:
        text: Größenangabe wie "203.45 KB", "1,5 MB", "820 KB", "1 GB", "512 Bytes"

    Returns:
        Größe in Bytes (int) oder None falls nicht parsbar
    """
    if not text or not text.strip():
        return None

    m = SIZE_PATTERN.match(text.strip())
    if not m:
        return None

    value_str = m.group(1).replace(",", ".")
    unit = m.group(2).lower()

    try:
        value = float(value_str)
    except ValueError:
        return None

    if unit == "kb":
        return int(round(value * 1024))
    elif unit == "mb":
        return int(round(value * 1024 * 1024))
    elif unit == "gb":
        return int(round(value * 1024 * 1024 * 1024))
    elif unit in ("bytes", "byte"):
        return int(round(value))
    return None


def parse_date(text: str, reference_date: datetime | None = None) -> str | None:
    """Datum in ISO 8601 (Europe/Berlin) parsen.

    Unterstützt:
    - Absolut: "25. Sep 2026, 10:12"
    - Relativ: "Heute, 09:15", "Gestern, 14:30", "Morgen, 08:00"

    Args:
        text: Datumsstring
        reference_date: Referenzdatum für relative Angaben (Default: jetzt in Europe/Berlin)

    Returns:
        ISO 8601 String (z. B. "2026-09-25T10:12:00+02:00") oder None
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Absolutes Datum
    m = DATE_PATTERN.match(text)
    if m:
        day = int(m.group(1))
        month_str = m.group(2)
        year = int(m.group(3))
        hour = int(m.group(4))
        minute = int(m.group(5))

        month = GERMAN_MONTHS.get(month_str)
        if month is None:
            return None

        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Berlin"))
            return dt.isoformat()
        except ValueError:
            return None

    # Relatives Datum
    m = RELATIVE_DATE_PATTERN.match(text)
    if m:
        if reference_date is None:
            reference_date = datetime.now(ZoneInfo("Europe/Berlin"))
        elif reference_date.tzinfo is None:
            reference_date = reference_date.replace(tzinfo=ZoneInfo("Europe/Berlin"))

        rel = m.group(1).lower()
        hour = int(m.group(2))
        minute = int(m.group(3))

        from datetime import timedelta
        if rel == "heute":
            target = reference_date
        elif rel == "gestern":
            target = reference_date - timedelta(days=1)
        elif rel == "morgen":
            target = reference_date + timedelta(days=1)
        else:
            return None

        try:
            dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=ZoneInfo("Europe/Berlin"))
            return dt.isoformat()
        except ValueError:
            return None

    return None


def extract_suffix(props: list[str]) -> str | None:
    """Dateiendung aus den Eigenschaften extrahieren (1. Eigenschaft, klein).

    Args:
        props: Liste der Eigenschafts-Strings (z. B. ["pdf", "1.5 MB", ...])

    Returns:
        Endung in Kleinbuchstaben oder None
    """
    if not props:
        return None
    first = props[0].strip().lower()
    # Erste "Wort" als Endung nehmen (vor Leerzeichen/Komma)
    return first.split()[0] if first else None


def extract_file_props(props: list[str]) -> dict:
    """Alle Datei-Eigenschaften extrahieren: size, size_text, timemodified, suffix.

    Args:
        props: Liste der Eigenschafts-Strings

    Returns:
        Dict mit size (int|None), size_text (str|None), timemodified (str|None), suffix (str|None)
    """
    result = {
        "size": None,
        "size_text": None,
        "timemodified": None,
        "suffix": None,
    }

    if not props:
        return result

    # Erste Eigenschaft = Endung
    result["suffix"] = extract_suffix(props)

    # Größe und Datum in allen Eigenschaften suchen (nicht positionsabhängig)
    for prop in props:
        prop = prop.strip()
        if not prop:
            continue

        # Größe versuchen
        if result["size"] is None:
            size = parse_size(prop)
            if size is not None:
                result["size"] = size
                result["size_text"] = prop
                continue

        # Datum versuchen
        if result["timemodified"] is None:
            date = parse_date(prop)
            if date is not None:
                result["timemodified"] = date
                continue

    return result