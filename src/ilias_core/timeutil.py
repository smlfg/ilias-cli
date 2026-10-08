"""Zeitstempel in ISO 8601 mit Zeitzone Europe/Berlin (N5).

Moodle liefert Unix-Zeitstempel; daraus werden hier die ISO-Strings für `--json`
und die Semesternamen für die Kursliste abgeleitet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:  # pragma: no cover - plattformabhängig
    from zoneinfo import ZoneInfo

    _BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover - ohne tzdata (z. B. Windows ohne tzdata)
    _BERLIN = timezone(timedelta(hours=2), "CEST")


def now() -> datetime:
    return datetime.now(_BERLIN)


def now_iso() -> str:
    """ISO-8601-Zeitstempel in Europe/Berlin, z. B. 2026-10-08T09:12:33+02:00."""
    return now().isoformat(timespec="seconds")


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_BERLIN)
    return value.isoformat(timespec="seconds")


def from_timestamp(value: float) -> datetime:
    """Unix-Zeitstempel -> Zeitpunkt in Europe/Berlin."""
    return datetime.fromtimestamp(float(value), _BERLIN)


def iso_or_none(value: object) -> str | None:
    """Unix-Zeitstempel -> ISO 8601 (Europe/Berlin).

    `0`, `None` und Werte, die kein Zeitstempel sind, ergeben `None` - Moodle
    benutzt 0 für "kein Datum gesetzt" (das wäre sonst 1970).
    """
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not value:
        return None
    try:
        return to_iso(from_timestamp(value))
    except (OverflowError, OSError, ValueError):  # pragma: no cover - absurte Werte
        return None


# --------------------------------------------------------------------- Semester
def semester_from_timestamp(value: object) -> str | None:
    """Semester aus dem Kurs-Startdatum (Unix-Zeitstempel, Europe/Berlin).

    * April bis September -> ``SoSe YYYY``
    * Oktober bis Dezember -> ``WiSe YYYY/YY`` (Folgejahr)
    * Januar bis März -> ``WiSe (YYYY-1)/YY`` (z. B. Start 01.02.2027 -> ``WiSe 2026/27``)

    Startdatum 0 bzw. fehlend -> `None` (Semester unbekannt).
    """
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not value:
        return None
    try:
        moment = from_timestamp(value)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - absurte Werte
        return None
    year = moment.year
    month = moment.month
    if 4 <= month <= 9:
        return f"SoSe {year}"
    if month >= 10:
        return f"WiSe {year}/{(year + 1) % 100:02d}"
    return f"WiSe {year - 1}/{year % 100:02d}"


def semester_year(semester: str | None) -> int:
    """Startjahr eines Semesternamens (``WiSe 2026/27`` -> 2026); unbekannt -> 0."""
    if not semester:
        return 0
    for token in semester.replace("/", " ").split():
        if len(token) == 4 and token.isdigit():
            return int(token)
    return 0
