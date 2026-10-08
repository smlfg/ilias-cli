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
    candidates: list[dict[str, Any]] | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.error_code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        if self.candidates is not None:
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


# ------------------------------------------------------------------ F2/F3: Kurse und Inhalte (Moodle)


@dataclass(frozen=True)
class Course:
    """Ein Moodle-Kurs aus `core_enrol_get_users_courses` (F2)."""

    id: int
    fullname: str
    shortname: str
    category: int | None = None
    semester: str | None = None
    visible: bool = True
    startdate: str | None = None
    enddate: str | None = None
    url: str | None = None

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

    def candidate_dict(self) -> dict[str, Any]:
        return {"id": self.id, "shortname": self.shortname, "fullname": self.fullname}


@dataclass(frozen=True)
class CoursesResult:
    """Kursliste eines Benutzers (F2). Bereits sortiert: neuestes Semester zuerst."""

    instance: str
    lms: str
    courses: tuple[Course, ...] = ()
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "courses",
            "instance": self.instance,
            "lms": self.lms,
            "count": len(self.courses),
            "courses": [c.to_json_dict() for c in self.courses],
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class FileChild:
    """Datei in einem Modul (`type == "file"`)."""

    type: str = "file"
    name: str = ""
    path: str = "/"
    size: int | None = None
    mimetype: str | None = None
    timemodified: str | None = None
    fileurl: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "file",
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "mimetype": self.mimetype,
            "timemodified": self.timemodified,
            "fileurl": self.fileurl,
        }


@dataclass(frozen=True)
class FolderChild:
    """Verschachtelter Ordner aus `filepath` eines `folder`-Moduls."""

    name: str = ""
    path: str = "/"
    children: tuple[Any, ...] = ()
    type: str = "folder"

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "folder",
            "name": self.name,
            "path": self.path,
            "children": [c.to_json_dict() for c in self.children],
        }


@dataclass(frozen=True)
class UrlChild:
    """Externer Link aus einem `url`-Modul."""

    name: str = ""
    url: str | None = None
    type: str = "url"

    def to_json_dict(self) -> dict[str, Any]:
        return {"type": "url", "name": self.name, "url": self.url}


@dataclass(frozen=True)
class ModuleInfo:
    """Ein Kursbaustein (Aktivität/Arbeitsmaterial) mit verschachtelten Kindern."""

    id: int = 0
    name: str = ""
    modname: str = ""
    url: str | None = None
    visible: bool = True
    uservisible: bool = True
    availability: str | None = None
    children: tuple[Any, ...] = ()

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


@dataclass(frozen=True)
class SectionInfo:
    """Ein Kursabschnitt mit seinen Bausteinen."""

    id: int = 0
    number: int = 0
    name: str = ""
    visible: bool = True
    uservisible: bool = True
    modules: tuple[ModuleInfo, ...] = ()

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
    """Kursinhalt als Baum: Kurs -> Abschnitte -> Bausteine -> Dateien/Ordner (F3)."""

    instance: str = ""
    lms: str = ""
    course: Course | None = None
    depth: int | None = None
    sections: tuple[SectionInfo, ...] = ()
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        course = self.course
        return {
            "ok": True,
            "command": "ls",
            "instance": self.instance,
            "lms": self.lms,
            "course": course.candidate_dict() if course else None,
            "depth": self.depth,
            "sections": [s.to_json_dict() for s in self.sections],
            "timestamp": self.timestamp,
        }
