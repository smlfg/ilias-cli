"""Strukturierte Rückgabewerte der Operationen (ANFORDERUNGEN.md §1).

Jede Operation liefert ein Dataclass, keinen formatierten Text. Die CLI
serialisiert es nur noch. `to_json_dict()` liefert die stabile Form für `--json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .secrets import Secret
from .timeutil import now_iso, semester_from_timestamp, timestamp_to_iso_berlin


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


@dataclass(frozen=True)
class Course:
    """Ein Moodle-Kurs aus core_enrol_get_users_courses."""

    id: int
    fullname: str
    shortname: str
    category: int | None = None
    semester: str | None = None
    visible: bool = True
    startdate: str | None = None
    enddate: str | None = None
    url: str | None = None

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any], base_url: str) -> Course:
        course_id = data.get("id")
        if not isinstance(course_id, int) or isinstance(course_id, bool):
            raise ValueError("Course id muss eine Integer sein")

        fullname = data.get("fullname", "")
        shortname = data.get("shortname", "")

        category = data.get("category")
        if not isinstance(category, int) or isinstance(category, bool):
            category = None

        visible = data.get("visible", 1)
        if not isinstance(visible, int) or isinstance(visible, bool):
            visible = bool(visible)
        else:
            visible = bool(visible)

        startdate_ts = data.get("startdate")
        if not isinstance(startdate_ts, int) or isinstance(startdate_ts, bool):
            startdate_ts = 0

        enddate_ts = data.get("enddate")
        if not isinstance(enddate_ts, int) or isinstance(enddate_ts, bool):
            enddate_ts = 0

        startdate = timestamp_to_iso_berlin(startdate_ts)
        enddate = timestamp_to_iso_berlin(enddate_ts)
        semester = semester_from_timestamp(startdate_ts)

        url = f"{base_url}/course/view.php?id={course_id}"

        return cls(
            id=course_id,
            fullname=fullname,
            shortname=shortname,
            category=category,
            semester=semester,
            visible=visible,
            startdate=startdate,
            enddate=enddate,
            url=url,
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
class CoursesResult:
    """Ergebnis von `ilias courses`."""

    instance: str
    lms: str
    count: int
    courses: tuple[Course, ...]
    timestamp: str = field(default_factory=now_iso)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "lms": self.lms,
            "count": self.count,
            "courses": [c.to_json_dict() for c in self.courses],
            "timestamp": self.timestamp,
        }


# --- Course Contents (ilias ls) -----------------------------------------


@dataclass(frozen=True)
class CourseFile:
    """Eine Datei in einem Ordner-Modul."""

    name: str
    path: str
    size: int
    mimetype: str | None
    timemodified: str | None
    fileurl: str

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any], base_path: str = "") -> CourseFile:
        name = data.get("filename", "")
        filepath = data.get("filepath", "/")
        # filepath z.B. "/Blatt 1/" -> relativ zu base_path
        path = (base_path + filepath).rstrip("/")
        size = data.get("filesize", 0)
        if not isinstance(size, int) or isinstance(size, bool):
            size = 0
        mimetype = data.get("mimetype")
        timemodified_ts = data.get("timemodified")
        timemodified = timestamp_to_iso_berlin(timemodified_ts) if isinstance(timemodified_ts, int) else None
        fileurl = data.get("fileurl", "")
        return cls(
            name=name,
            path=path,
            size=size,
            mimetype=mimetype,
            timemodified=timemodified,
            fileurl=fileurl,
        )

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
class CourseFolder:
    """Ein Ordner (kann Unterordner und Dateien enthalten)."""

    name: str
    path: str
    children: tuple[CourseFile | CourseFolder, ...] = ()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "folder",
            "name": self.name,
            "path": self.path,
            "children": [c.to_json_dict() for c in self.children],
        }


@dataclass(frozen=True)
class CourseURL:
    """Ein URL-Modul."""

    name: str
    url: str

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any]) -> CourseURL:
        name = data.get("filename", data.get("name", "Link"))
        url = data.get("fileurl", "")
        return cls(name=name, url=url)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": "url",
            "name": self.name,
            "url": self.url,
        }


@dataclass(frozen=True)
class CourseModule:
    """Ein Modul/Aktivität in einem Abschnitt."""

    id: int
    name: str
    modname: str
    url: str | None = None
    visible: bool = True
    uservisible: bool = True
    availability: str | None = None
    children: tuple[CourseFile | CourseFolder | CourseURL, ...] = ()

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any]) -> CourseModule:
        module_id = data.get("id")
        if not isinstance(module_id, int) or isinstance(module_id, bool):
            raise ValueError("Module id muss eine Integer sein")

        name = data.get("name", "")
        modname = data.get("modname", "")
        url = data.get("url")
        visible = data.get("visible", 1)
        if not isinstance(visible, int) or isinstance(visible, bool):
            visible = bool(visible)
        else:
            visible = bool(visible)
        uservisible = data.get("uservisible", True)
        if not isinstance(uservisible, bool):
            uservisible = bool(uservisible)
        availability = data.get("availabilityinfo")
        if isinstance(availability, str):
            # HTML-Strip für Anzeige
            import re
            availability = re.sub(r"<[^>]+>", "", availability).strip()
            if not availability:
                availability = None

        children: list[CourseFile | CourseFolder | CourseURL] = []
        contents = data.get("contents") or []
        if modname == "folder":
            # Ordner: Inhalte zu Folder-Struktur aufbauen
            children = _build_folder_structure(contents)
        elif modname == "resource":
            # Ressource: Dateien
            for item in contents:
                if item.get("type") == "file":
                    children.append(CourseFile.from_moodle_json(item))
        elif modname == "url":
            # URL-Modul
            for item in contents:
                if item.get("type") == "url":
                    children.append(CourseURL.from_moodle_json(item))
        # andere Modul-Typen (assign, forum, quiz, page, label, choice, lti, ...) haben keine Kinder

        return cls(
            id=module_id,
            name=name,
            modname=modname,
            url=url,
            visible=visible,
            uservisible=uservisible,
            availability=availability,
            children=tuple(children),
        )

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


def _build_folder_structure(contents: list[dict[str, Any]]) -> list[CourseFile | CourseFolder]:
    """Baut aus Moodle folder contents (mit filepath) eine verschachtelte Folder-Struktur.
    
    filepath-Beispiele: "/", "/Blatt 1/", "/Blatt 1/Loesungen/"
    """
    # Erst alle Dateien nach Pfad gruppieren
    from collections import defaultdict

    path_to_files: defaultdict[str, list[CourseFile]] = defaultdict(list)
    for item in contents:
        if item.get("type") == "file":
            cf = CourseFile.from_moodle_json(item)
            path_to_files[cf.path].append(cf)

    # Alle Pfade sammeln (Verzeichnisse)
    all_paths = set(path_to_files.keys())
    for path in list(all_paths):
        # Eltern-Pfade hinzufügen
        parts = path.strip("/").split("/")
        for i in range(1, len(parts)):
            parent = "/" + "/".join(parts[:i]) + "/"
            all_paths.add(parent)
    all_paths.add("/")  # Wurzel

    # Folder-Objekte bottom-up bauen
    path_to_folder: dict[str, CourseFolder] = {}
    # Sortiere Pfade nach Tiefe (tiefste zuerst)
    sorted_paths = sorted(all_paths, key=lambda p: p.count("/"), reverse=True)

    for path in sorted_paths:
        name = path.strip("/").split("/")[-1] if path != "/" else "Wurzel"
        if path == "/":
            name = "Wurzel"
        child_folders = []
        child_files = []
        # Direkte Kinder finden
        for other_path, files in path_to_files.items():
            if other_path == path:
                child_files.extend(files)
            elif other_path.startswith(path) and other_path != path:
                # Prüfen ob direktes Kind (ein weiteres / nach path)
                rest = other_path[len(path):].lstrip("/")
                if "/" not in rest:
                    # Direkte Datei in diesem Ordner (aber nicht in Unterordner)
                    pass  # wird über Folder-Struktur gehandhabt
        # Unterordner als Kinder
        for other_path in all_paths:
            if other_path == path:
                continue
            if other_path.startswith(path) and other_path != path:
                rest = other_path[len(path):].lstrip("/")
                if "/" not in rest:
                    # Direktes Kind
                    if other_path in path_to_folder:
                        child_folders.append(path_to_folder[other_path])

        # Dateien direkt in diesem Ordner (nicht in Unterordnern)
        direct_files = []
        for other_path, files in path_to_files.items():
            if other_path == path:
                direct_files.extend(files)
            elif other_path.startswith(path + "/") and other_path != path:
                rest = other_path[len(path) + 1:]
                if "/" not in rest:
                    direct_files.extend(files)

        all_children: list[CourseFile | CourseFolder] = []
        all_children.extend(sorted(child_folders, key=lambda f: f.name))
        all_children.extend(sorted(direct_files, key=lambda f: f.name))

        folder = CourseFolder(name=name, path=path, children=tuple(all_children))
        path_to_folder[path] = folder

    # Nur den Wurzel-Ordner zurückgeben
    root = path_to_folder.get("/")
    if root:
        return [root]
    return []


@dataclass(frozen=True)
class CourseSection:
    """Ein Abschnitt/Topic in einem Kurs."""

    id: int
    number: int
    name: str
    visible: bool
    uservisible: bool
    modules: tuple[CourseModule, ...] = ()

    @classmethod
    def from_moodle_json(cls, data: dict[str, Any]) -> CourseSection:
        section_id = data.get("id")
        if not isinstance(section_id, int) or isinstance(section_id, bool):
            raise ValueError("Section id muss eine Integer sein")

        number = data.get("section", 0)
        if not isinstance(number, int) or isinstance(number, bool):
            number = 0

        name = data.get("name", "")
        visible = data.get("visible", 1)
        if not isinstance(visible, int) or isinstance(visible, bool):
            visible = bool(visible)
        else:
            visible = bool(visible)
        uservisible = data.get("uservisible", True)
        if not isinstance(uservisible, bool):
            uservisible = bool(uservisible)

        modules = []
        for mod_data in data.get("modules") or []:
            try:
                modules.append(CourseModule.from_moodle_json(mod_data))
            except Exception:
                # Fehlende/kaputte Module überspringen
                pass

        return cls(
            id=section_id,
            number=number,
            name=name,
            visible=visible,
            uservisible=uservisible,
            modules=tuple(modules),
        )

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
class CourseContentsResult:
    """Ergebnis von `ilias ls <kurs>`."""

    instance: str
    lms: str
    course: dict[str, Any]  # {id, fullname, shortname}
    depth: int | None
    sections: tuple[CourseSection, ...]
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
