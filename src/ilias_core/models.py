"""Strukturierte Datenmodelle der ILIAS-/Moodle-CLI (ANFORDERUNGEN.md §1).

Die Modelle enthalten bewusst **keine** Cookies, Passwörter, Tokens oder Secrets.
Sie sind die einzige Oberfläche, die an CLI oder MCP weitergegeben wird.

- ILIAS (Web-Session): ``LoginResult``, ``SessionStatus`` mit ``to_dict()``.
- Moodle (Webservice-Token): ``MoodleLoginResult``, ``MoodleStatusResult``, ``LogoutResult``.
- F2/F3 (backend-neutral): ``Course``, ``CoursesResult``, ``Section``, ``Module``,
  ``FolderNode``/``FileNode``/``UrlNode``, ``CourseContentsResult``.
- Fehler: ``ErrorResult`` (gemeinsame ``--json``-Form für alle Befehle).
`to_json_dict()` liefert die stabile Form für `--json`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .secrets import Secret
from .timeutil import now_iso, semester_order


@dataclass(frozen=True)
class LoginResult:
    """Ergebnis eines erfolgreichen, verifizierten Logins."""

    authenticated: bool
    base_url: str
    client_id: str
    method: str = "oidc-keycloak"
    message: str = ""
    instance: str = "hhn"
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionStatus:
    """Ergebnis einer Session-Gültigkeitsprüfung."""

    authenticated: bool
    base_url: str
    client_id: str
    message: str = ""
    instance: str = "hhn"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------- Moodle + F2/F3

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
class MoodleLoginResult:
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
class MoodleStatusResult:
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
    error_type: str | None = None
    hint: str | None = None
    instance: str | None = None
    lms: str | None = None
    candidates: list[dict[str, Any]] | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.error_code, "message": self.message}
        if self.error_type:
            error["type"] = self.error_type
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
            "message": self.message,
            "exit_code": self.exit_code,
            "timestamp": self.timestamp,
        }
        return data


# --------------------------------------------------------------- F2/F3: Kurse
@dataclass(frozen=True)
class Course:
    """Ein Kurs aus core_enrol_get_users_courses (Moodle-REST) oder ILIAS-Mitgliedschaft."""

    id: int
    fullname: str
    shortname: str
    category: int | None = None
    semester: str | None = None
    visible: bool = True
    startdate: str | None = None
    enddate: str | None = None
    url: str = ""
    description: str = ""

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
            "description": self.description,
        }

    def to_ref_dict(self) -> dict[str, Any]:
        return {"id": self.id, "fullname": self.fullname, "shortname": self.shortname}

    def sort_key(self) -> tuple[bool, int, str]:
        """Sortierung: Semester neueste zuerst, None zuletzt, dann fullname."""
        return (self.semester is None, -semester_order(self.semester), self.fullname.lower())


@dataclass(frozen=True)
class CoursesResult:
    instance: str
    lms: str
    courses: list[Course] = field(default_factory=list)
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "count": len(self.courses),
            "courses": [course.to_json_dict() for course in self.courses],
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ContentNodeBase:
    """Basisklasse für alle Inhalts-Knoten (Ordner, Dateien, Links, Items, etc.)."""

    def to_json_dict(self) -> dict[str, Any]:
        # Alle Felder serialisieren, None-Werte weglassen
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class FolderNode(ContentNodeBase):
    name: str
    path: str
    ref_id: int | None = None
    url: str | None = None
    visible: bool = True
    children: list["ContentNodeBase"] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "folder",
            "name": self.name,
            "path": self.path,
            "ref_id": self.ref_id,
            "url": self.url,
            "visible": self.visible,
            "children": [child.to_json_dict() for child in self.children],
        }


@dataclass(frozen=True)
class FileNode(ContentNodeBase):
    name: str
    path: str
    fileurl: str
    ref_id: int | None = None
    size: int | None = None
    size_text: str | None = None
    suffix: str | None = None
    mimetype: str | None = None
    timemodified: str | None = None
    visible: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        d = {"type": "file"}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d


@dataclass(frozen=True)
class UrlNode(ContentNodeBase):
    name: str
    url: str
    ref_id: int | None = None
    visible: bool = True
    target_url: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        d = {"type": "url"}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d


@dataclass(frozen=True)
class ItemNode(ContentNodeBase):
    """Generisches Item (Übung, Test, Forum, Wiki, etc.)."""
    name: str
    modname: str  # exc, tst, frm, wiki, etc.
    ref_id: int | None = None
    url: str | None = None
    visible: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        d = {"type": "item", "modname": self.modname}
        for k, v in self.__dict__.items():
            if v is not None and k != "modname":
                d[k] = v
        return d


@dataclass(frozen=True)
class CourseLinkNode(ContentNodeBase):
    name: str
    ref_id: int
    url: str
    target_ref_id: int
    visible: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        d = {"type": "course_link"}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d


@dataclass(frozen=True)
class SessionNode(ContentNodeBase):
    name: str
    ref_id: int
    url: str
    visible: bool = True
    children: None = None  # Spec §13.6: sessions nicht expandieren

    def to_json_dict(self) -> dict[str, Any]:
        d = {"type": "session", "children": None}
        for k, v in self.__dict__.items():
            if v is not None and k != "children":
                d[k] = v
        return d


ContentNode = FolderNode | FileNode | UrlNode | ItemNode | CourseLinkNode | SessionNode


@dataclass(frozen=True)
class Module:
    id: int
    name: str
    modname: str
    url: str | None = None
    visible: bool = True
    uservisible: bool = True
    availability: str | None = None
    children: list[ContentNode] | None = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        children = self.children
        if children is None:
            children_json = None
        else:
            children_json = [child.to_json_dict() for child in children]
        return {
            "id": self.id,
            "name": self.name,
            "modname": self.modname,
            "url": self.url,
            "visible": self.visible,
            "uservisible": self.uservisible,
            "availability": self.availability,
            "children": children_json,
        }


@dataclass(frozen=True)
class Section:
    id: int
    number: int
    name: str
    visible: bool = True
    uservisible: bool = True
    modules: list[Module] = field(default_factory=list)

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
    instance: str
    lms: str
    course: dict[str, Any]
    sections: list[Section] = field(default_factory=list)
    depth: int | None = None
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "course": self.course,
            "depth": self.depth,
            "sections": [section.to_json_dict() for section in self.sections],
            "timestamp": self.timestamp,
        }
