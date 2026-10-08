"""Strukturierte Rückgabewerte der Operationen (ANFORDERUNGEN.md §1).

Jede Operation liefert ein Dataclass, keinen formatierten Text. Die CLI
serialisiert es nur noch. `to_json_dict()` liefert die stabile Form für `--json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import ParseError
from .secrets import Secret
from .text import plain_text
from .timeutil import iso_or_none, now_iso, semester_from_timestamp


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
    details: dict[str, Any] | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.error_code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        for key, value in (self.details or {}).items():
            error[key] = value
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


# --------------------------------------------------------------------- F2/F3: Kurse
@dataclass(frozen=True)
class Course:
    """Ein eigener Kurs (Moodle `core_enrol_get_users_courses`)."""

    id: int
    fullname: str
    shortname: str
    category: int | None = None
    semester: str | None = None
    visible: bool = True
    startdate: str | None = None
    enddate: str | None = None
    url: str = ""

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any], *, base_url: str) -> "Course":
        """Ein Kursobjekt aus der REST-Antwort. Fehlende Pflichtfelder -> Exit 5."""
        course_id = data.get("id")
        if not isinstance(course_id, int) or isinstance(course_id, bool):
            raise ParseError(
                "core_enrol_get_users_courses: Kursobjekt ohne gültige 'id'.",
                hint="Unerwartetes Antwortformat der Moodle-Instanz.",
            )
        category = data.get("category")
        if not isinstance(category, int) or isinstance(category, bool):
            category = None
        return cls(
            id=course_id,
            fullname=plain_text(data.get("fullname")) or f"Kurs {course_id}",
            shortname=plain_text(data.get("shortname")) or str(course_id),
            category=category,
            semester=semester_from_timestamp(data.get("startdate")),
            visible=as_bool(data.get("visible"), default=True),
            startdate=iso_or_none(data.get("startdate")),
            enddate=iso_or_none(data.get("enddate")),
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


@dataclass(frozen=True)
class CourseRef:
    """Kurs-Kopfzeile (für `ls`): id, fullname, shortname."""

    id: int
    fullname: str
    shortname: str

    def to_json_dict(self) -> dict[str, Any]:
        return {"id": self.id, "fullname": self.fullname, "shortname": self.shortname}


@dataclass(frozen=True)
class CourseListResult:
    """Ergebnis von `ilias courses` (F2)."""

    instance: str
    lms: str
    courses: tuple[Course, ...] = ()
    timestamp: str = field(default_factory=now_iso)

    @property
    def count(self) -> int:
        return len(self.courses)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "count": self.count,
            "courses": [course.to_json_dict() for course in self.courses],
            "timestamp": self.timestamp,
        }


# --------------------------------------------------------------------- F3: Baum
@dataclass(frozen=True)
class FileNode:
    """Datei in einem Modul (`type` = file)."""

    name: str
    path: str = "/"
    size: int | None = None
    mimetype: str | None = None
    timemodified: str | None = None
    fileurl: str | None = None

    @property
    def type(self) -> str:
        return "file"

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
class FolderNode:
    """Unterordner innerhalb eines Moduls (`type` = folder)."""

    name: str
    path: str = "/"
    children: tuple[Any, ...] = ()

    @property
    def type(self) -> str:
        return "folder"

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "folder",
            "name": self.name,
            "path": self.path,
            "children": [child.to_json_dict() for child in self.children],
        }


@dataclass(frozen=True)
class UrlNode:
    """Ziel eines `url`-Moduls (`type` = url)."""

    name: str
    url: str

    @property
    def type(self) -> str:
        return "url"

    def to_json_dict(self) -> dict[str, Any]:
        return {"type": "url", "name": self.name, "url": self.url}


ContentNode = FileNode | FolderNode | UrlNode


@dataclass(frozen=True)
class ModuleNode:
    """Ein Inhaltselement (Aktivität) eines Kurses."""

    id: int
    name: str
    modname: str
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
            "children": [child.to_json_dict() for child in self.children],
        }


@dataclass(frozen=True)
class SectionNode:
    """Ein Kursabschnitt mit seinen Modulen."""

    id: int
    number: int = 0
    name: str = ""
    visible: bool = True
    uservisible: bool = True
    modules: tuple[ModuleNode, ...] = ()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "visible": self.visible,
            "uservisible": self.uservisible,
            "modules": [module.to_json_dict() for module in self.modules],
        }


@dataclass(frozen=True)
class CourseContentsResult:
    """Ergebnis von `ilias ls <kurs>` (F3): Abschnitte -> Module -> Inhalte."""

    instance: str
    lms: str
    course: CourseRef
    sections: tuple[SectionNode, ...] = ()
    depth: int | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "course": self.course.to_json_dict(),
            "depth": self.depth,
            "sections": [section.to_json_dict() for section in self.sections],
            "timestamp": self.timestamp,
        }


def as_bool(value: object, *, default: bool) -> bool:
    """Moodle liefert 1/0, manchmal auch `true`/`false` oder gar nichts."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "none"}
    return default


def as_int(value: object) -> int | None:
    """int oder None - Moodle schickt Zahlen mal als String."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None
