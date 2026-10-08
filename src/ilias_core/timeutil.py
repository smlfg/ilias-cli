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


def berlin_tz():
    """Zeitzone Europe/Berlin (N5)."""
    return _BERLIN


def timestamp_to_iso(value: object) -> str | None:
    """Unix-Timestamp -> ISO 8601 in Europe/Berlin; 0/fehlend -> None."""
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    try:
        moment = datetime.fromtimestamp(value, tz=_BERLIN)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.isoformat(timespec="seconds")


def semester_label(startdate: object) -> str | None:
    """Semester aus dem Kurs-`startdate` ableiten (Europe/Berlin).

    Apr–Sep -> "SoSe YYYY", Okt–Dez -> "WiSe YYYY/YY+1",
    Jan–Mär -> "WiSe YYYY-1/YY". 0/fehlend -> None.
    """
    if isinstance(startdate, bool):
        return None
    if not isinstance(startdate, (int, float)):
        return None
    if startdate <= 0:
        return None
    try:
        moment = datetime.fromtimestamp(startdate, tz=_BERLIN)
    except (OverflowError, OSError, ValueError):
        return None
    year, month = moment.year, moment.month
    if 4 <= month <= 9:
        return f"SoSe {year}"
    if 10 <= month <= 12:
        return f"WiSe {year}/{str(year + 1)[-2:]}"
    return f"WiSe {year - 1}/{str(year)[-2:]}"


def semester_sort_key(semester: str | None) -> tuple[int, int]:
    """Sortierschlüssel: neueres Semester -> größer; None -> kleinster."""
    if not semester:
        return (-1, -1)
    try:
        if semester.startswith("SoSe "):
            return (int(semester[5:9]), 1)
        if semester.startswith("WiSe "):
            return (int(semester[5:9]), 2)
    except ValueError:
        return (-1, -1)
    return (-1, -1)
