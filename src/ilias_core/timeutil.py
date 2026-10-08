"""Zeitstempel in ISO 8601 mit Zeitzone Europe/Berlin (N5)."""

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


def timestamp_to_iso_berlin(timestamp: int | None) -> str | None:
    """Konvertiert einen Unix-Timestamp (Sekunden seit Epoch) in ISO 8601 (Europe/Berlin).
    Gibt None zurück, wenn timestamp 0, None oder negativ ist."""
    if not timestamp or timestamp <= 0:
        return None
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(_BERLIN)
    return dt.isoformat(timespec="seconds")


def semester_from_timestamp(timestamp: int | None) -> str | None:
    """Leitet das Semester aus einem Startdatum (Unix-Timestamp) ab.
    
    Monate Mar-Aug -> "SoSe YYYY"
    Monate Sep-Dec -> "WiSe YYYY/YY+1"  
    Monate Jan-Feb -> "WiSe YYYY-1/YY"
    
    Gibt None zurück, wenn timestamp 0, None oder negativ ist."""
    if not timestamp or timestamp <= 0:
        return None
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(_BERLIN)
    year = dt.year
    month = dt.month
    if 3 <= month <= 8:  # März bis August
        return f"SoSe {year}"
    elif 9 <= month <= 12:  # September bis Dezember
        return f"WiSe {year}/{str(year + 1)[-2:]}"
    else:  # Januar bis Februar
        return f"WiSe {year - 1}/{str(year)[-2:]}"
