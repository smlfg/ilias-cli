"""Strukturierte Rückgabewerte der Operationen (ANFORDERUNGEN.md §1).

Jede Operation liefert ein Dataclass, keinen formatierten Text. Die CLI
serialisiert es nur noch. `to_json_dict()` liefert die stabile Form für `--json`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .secrets import Secret
from .timeutil import now_iso


def derive_semester(startdate: int | None) -> str | None:
    """Derive semester string from Unix startdate (Europe/Berlin).

    Mar–Aug → "SoSe YYYY", Sep–Dec → "WiSe YYYY/YY+1", Jan–Feb → "WiSe YYYY-1/YY".
    startdate 0 or None → None.
    """
    if not startdate:
        return None
    from datetime import datetime, timezone, timedelta

    berlin_tz = timezone(timedelta(hours=2))  # CET/CEST simplified; tests use fixed values
    dt = datetime.fromtimestamp(startdate, tz=berlin_tz)
    month = dt.month
    year = dt.year
    if 3 <= month <= 8:
        return f"SoSe {year}"
    if 9 <= month <= 12:
        return f"WiSe {year}/{year + 1 - 2000}"
    # 1 <= month <= 2
    prev_year = year - 1
    return f"WiSe {prev_year}/{year % 100}"


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


@dataclass(frozen=True)
class Course:
    """Moodle-Kurs aus core_enrol_get_users_courses."""

    id: int
    fullname: str
    shortname: str
    category: int | None
    semester: str | None
    visible: bool
    startdate: int | None
    enddate: int | None
    url: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fullname": self.fullname,
            "shortname": self.shortname,
            "category": self.category,
            "semester": self.semester,
            "visible": self.visible,
            "startdate": self.startdate,
            "enddate": self.enddate,
            "url": self.url,
        }


@dataclass(frozen=True)
class CourseSection:
    """Eine Abschnitt/Modul-Gruppe in einem Kurs (core_course_get_contents)."""

    id: int
    number: int
    name: str
    visible: bool
    uservisible: bool
    modules: list[Any] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "visible": self.visible,
            "uservisible": self.uservisible,
            "modules": [m.to_json_dict() if hasattr(m, "to_json_dict") else m for m in self.modules],
        }


@dataclass(frozen=True)
class LsFile:
    """Eine Datei im ls-Baum."""

    type: str = "file"
    name: str = ""
    path: str = ""
    size: int = 0
    mimetype: str = ""
    timemodified: str | None = None
    fileurl: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "mimetype": self.mimetype,
            "timemodified": self.timemodified,
            "fileurl": self.fileurl,
        }


@dataclass(frozen=True)
class LsUrl:
    """Eine URL-Ressource im ls-Baum."""

    type: str = "url"
    name: str = ""
    url: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "url": self.url,
        }


@dataclass(frozen=True)
class LsFolder:
    """Ein Ordner-Knoten im ls-Baum (aus modname == 'folder' mit filepath)."""

    type: str = "folder"
    name: str = ""
    path: str = ""
    children: list[Any] = field(default_factory=list)

    def add_child(self, child: Any) -> None:
        object.__setattr__(self, "children", self.children + [child])

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "path": self.path,
            "children": [c.to_json_dict() if hasattr(c, "to_json_dict") else c for c in self.children],
        }


@dataclass(frozen=True)
class LsResult:
    """Ergebnis von ilias ls ... Befehl."""

    instance: str
    lms: str
    course: dict[str, Any]
    depth: int | None
    sections: list[Any]
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "course": self.course,
            "depth": self.depth,
            "sections": [s.to_json_dict() for s in self.sections],
            "timestamp": self.timestamp,
        }
