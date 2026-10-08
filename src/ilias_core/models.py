"""Strukturierte Rückgabewerte der Operationen (ANFORDERUNGEN.md §1).

Jede Operation liefert ein Dataclass, keinen formatierten Text. Die CLI
serialisiert es nur noch. `to_json_dict()` liefert die stabile Form für `--json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .secrets import Secret
from .timeutil import now_iso


@dataclass(frozen=True)
class SiteInfo:
    """Ergebnis von core_webservice_get_site_info (Moodle-REST)."""

    sitename: str
    username: str
    fullname: str
    userid: int | None = None
    siteurl: str | None = None
    release: str | None = None
    version: str | None = None
    lang: str | None = None

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any]) -> SiteInfo:
        def _s(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) and value else None

        userid = data.get("userid")
        if not isinstance(userid, int) or isinstance(userid, bool):
            userid = None
        return cls(
            sitename=_s("sitename") or "",
            username=_s("username") or "",
            fullname=_s("fullname") or "",
            userid=userid,
            siteurl=_s("siteurl"),
            release=_s("release"),
            version=_s("version"),
            lang=_s("lang"),
        )


@dataclass(frozen=True)
class LoginResult:
    instance: str
    lms: str
    base_url: str
    username: str
    fullname: str
    sitename: str
    userid: int | None = None
    verified: bool = True
    token_stored: bool = True
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "login",
            "instance": self.instance,
            "lms": self.lms,
            "base_url": self.base_url,
            "username": self.username,
            "fullname": self.fullname,
            "sitename": self.sitename,
            "userid": self.userid,
            "verified": self.verified,
            "token_stored": self.token_stored,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class StatusResult:
    instance: str
    lms: str
    base_url: str
    username: str
    fullname: str
    sitename: str
    userid: int | None = None
    logged_in: bool = True
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "status",
            "instance": self.instance,
            "lms": self.lms,
            "base_url": self.base_url,
            "username": self.username,
            "fullname": self.fullname,
            "sitename": self.sitename,
            "userid": self.userid,
            "logged_in": self.logged_in,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class LogoutResult:
    instance: str
    lms: str
    token_removed: bool = False
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "logout",
            "instance": self.instance,
            "lms": self.lms,
            "token_removed": self.token_removed,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class Credentials:
    """Benutzername + Passwort. `repr()` gibt das Passwort nie preis (A1)."""

    username: str
    password: Secret

    def __repr__(self) -> str:
        return f"Credentials(username={self.username!r}, password=***)"


@dataclass(frozen=True)
class ErrorResult:
    command: str
    error_code: str
    message: str
    exit_code: int
    hint: str | None = None
    instance: str | None = None
    lms: str | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.error_code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        data: dict[str, Any] = {
            "ok": False,
            "command": self.command,
            "instance": self.instance,
            "lms": self.lms,
            "error": error,
            "exit_code": self.exit_code,
            "timestamp": self.timestamp,
        }
        return data
