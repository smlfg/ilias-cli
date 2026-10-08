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

    candidates: list[dict[str, Any]] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.error_code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        if self.candidates:
            error["candidates"] = self.candidates
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


# ---------------------------------------------------------------- F2/F3
from datetime import datetime  # noqa: E402

from .timeutil import _BERLIN, epoch_iso  # noqa: E402


def semester_for_startdate(value: int | float | None) -> str | None:
    """Semester-Label aus dem Kursstart (Europe/Berlin), sonst None.

    Apr-Sep  -> "SoSe YYYY"
    Oct-Dez  -> "WiSe YYYY/YY+1"   (z. B. 2026-10-01 -> "WiSe 2026/27")
    Jan-Mar  -> "WiSe YYYY-1/YY"   (z. B. 2027-02-01 -> "WiSe 2026/27")
    """
    if not value or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        dt = datetime.fromtimestamp(value, _BERLIN)
    except (OverflowError, OSError, ValueError):  # pragma: no cover
        return None
    year, month = dt.year, dt.month
    if 4 <= month <= 9:
        return f"SoSe {year}"
    if month >= 10:
        return f"WiSe {year}/{(year + 1) % 100:02d}"
    return f"WiSe {year - 1}/{year % 100:02d}"


def semester_rank(semester: str | None) -> tuple[int, int]:
    """Sortierschlüssel: neueres Semester größer; None ganz unten."""
    if not semester:
        return (0, 0)
    try:
        kind, rest = semester.split(" ", 1)
        year = int(rest.split("/")[0])
        if kind == "SoSe":
            return (year, 2)
        if kind == "WiSe":
            return (year + 1, 1)
    except (ValueError, IndexError):  # pragma: no cover
        pass
    return (0, 0)


@dataclass(frozen=True)
class Course:
    id: int
    fullname: str
    shortname: str
    category: int | None
    semester: str | None
    visible: bool
    startdate: str | None
    enddate: str | None
    url: str

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any], base_url: str) -> "Course":
        def _s(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) and value else None

        course_id = data.get("id")
        if not isinstance(course_id, int) or isinstance(course_id, bool):
            raise ValueError("Kurs ohne numerische id")
        category = data.get("category")
        if not isinstance(category, int) or isinstance(category, bool):
            category = None
        start = data.get("startdate") if isinstance(data.get("startdate"), (int, float)) else None
        end = data.get("enddate") if isinstance(data.get("enddate"), (int, float)) else None
        return cls(
            id=course_id,
            fullname=_s("fullname") or "",
            shortname=_s("shortname") or "",
            category=category if category else None,
            semester=semester_for_startdate(start),
            visible=bool(data.get("visible", 1)),
            startdate=epoch_iso(start),
            enddate=epoch_iso(end),
            url=f"{base_url.rstrip('/')}/course/view.php?id={course_id}",
        )

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

    def candidate(self) -> dict[str, Any]:
        return {"id": self.id, "shortname": self.shortname, "fullname": self.fullname}


@dataclass(frozen=True)
class CoursesResult:
    instance: str
    lms: str
    courses: tuple[Course, ...]
    timestamp: str = field(default_factory=now_iso)

    @property
    def count(self) -> int:
        return len(self.courses)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "count": self.count,
            "courses": [c.to_json_dict() for c in self.courses],
            "timestamp": self.timestamp,
        }


@dataclass
class ContentNode:
    """Ein Knoten unterhalb eines Moduls (Ordner, Datei, externer Link)."""

    type: str  # "folder" | "file" | "url"
    name: str
    path: str | None = None
    size: int | None = None
    mimetype: str | None = None
    timemodified: str | None = None
    fileurl: str | None = None
    url: str | None = None
    children: list["ContentNode"] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        if self.type == "folder":
            return {
                "type": "folder",
                "name": self.name,
                "path": self.path,
                "children": [c.to_json_dict() for c in self.children],
            }
        if self.type == "url":
            return {"type": "url", "name": self.name, "url": self.url}
        return {
            "type": "file",
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "mimetype": self.mimetype,
            "timemodified": self.timemodified,
            "fileurl": self.fileurl,
        }


@dataclass
class ModuleNode:
    id: int | None
    name: str
    modname: str
    url: str | None
    visible: bool
    uservisible: bool
    availability: str | None = None
    children: list[ContentNode] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "modname": self.modname,
            "url": self.url,
            "visible": self.visible,
            "uservisible": self.uservisible,
            "availability": self.availability,
            "children": [c.to_json_dict() for c in self.children],
        }


@dataclass
class SectionNode:
    id: int | None
    number: int | None
    name: str
    visible: bool
    uservisible: bool
    modules: list[ModuleNode] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "visible": self.visible,
            "uservisible": self.uservisible,
            "modules": [m.to_json_dict() for m in self.modules],
        }


@dataclass(frozen=True)
class LsResult:
    instance: str
    lms: str
    course: dict[str, Any]
    depth: int | None
    sections: tuple[SectionNode, ...]
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
