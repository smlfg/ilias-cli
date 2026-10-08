"""Strukturierte Rückgabemodelle (ANFORDERUNGEN.md §1).

Operationen liefern Daten, keinen formatierten Text. Die CLI rendert daraus
JSON oder eine menschliche Tabelle. ``to_dict`` ist bewusst JSON-freundlich
(Datetimes als ISO 8601 mit Zeitzone).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

try:  # Europe/Berlin aus der System-Zeitzonendatenbank
    from zoneinfo import ZoneInfo

    BERLIN_TZ: timezone | ZoneInfo = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover - Fallback ohne tzdata (z. B. Windows)
    BERLIN_TZ = timezone(timedelta(hours=1), "Europe/Berlin")


def now_berlin() -> datetime:
    """Aktuelle Zeit in Europe/Berlin (ISO 8601 mit Offset)."""
    return datetime.now(BERLIN_TZ)


@dataclass
class SiteInfo:
    """Antwort von core_webservice_get_site_info."""

    sitename: str
    username: str
    fullname: str
    userid: int | None = None
    siteurl: str | None = None


@dataclass
class LoginResult:
    lms: str
    instance: str
    base_url: str
    username: str
    fullname: str
    sitename: str
    userid: int | None
    logged_in_at: datetime

    def to_dict(self) -> dict:
        data = asdict(self)
        data["logged_in_at"] = self.logged_in_at.isoformat()
        return data


@dataclass
class StatusResult:
    lms: str
    instance: str
    base_url: str
    username: str
    fullname: str
    sitename: str
    userid: int | None
    valid: bool
    checked_at: datetime

    def to_dict(self) -> dict:
        data = asdict(self)
        data["checked_at"] = self.checked_at.isoformat()
        return data


@dataclass
class LogoutResult:
    lms: str
    instance: str
    base_url: str
    removed: bool
    logged_out_at: datetime

    def to_dict(self) -> dict:
        data = asdict(self)
        data["logged_out_at"] = self.logged_out_at.isoformat()
        return data
