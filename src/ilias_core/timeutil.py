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
