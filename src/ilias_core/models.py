"""Datenmodelle (strukturiert, kein formatierter Text).

``LoginResult`` enthält die Cookies intern (für den Store), aber niemals
in ``public_dict()`` - Cookies werden nie ausgeben, auch nicht in
``status --json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LoginResult:
    """Ergebnis eines erfolgreichen Logins."""

    cookies: dict[str, str] = field(default_factory=dict)
    final_url: str = ""

    def public_dict(self) -> dict:
        """Öffentliche Ansicht OHNE Cookies (für JSON-Ausgabe)."""
        return {
            "logged_in": True,
            "final_url": self.final_url,
        }


@dataclass
class SessionStatus:
    """Ergebnis einer Gültigkeitsprüfung."""

    logged_in: bool
    base_url: str
    client_id: str
    checked_at: datetime
    message: str

    def to_dict(self) -> dict:
        return {
            "logged_in": self.logged_in,
            "base_url": self.base_url,
            "client_id": self.client_id,
            "checked_at": self.checked_at.isoformat(),
            "message": self.message,
        }


@dataclass
class SessionData:
    """Persistierte Session (Cookies + Kontext)."""

    base_url: str
    client_id: str
    cookies: dict[str, str]
    username: str | None = None
    created_at: datetime | None = None
