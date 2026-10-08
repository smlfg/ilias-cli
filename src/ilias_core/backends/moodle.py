"""Moodle-Backend: Login/Status/Logout über den offiziellen Moodle-Mobile-Webservice.

Geprüft am 08.10.2026 (siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):
`enablewebservices = 1`, `enablemobilewebservice = 1`, `typeoflogin = 1`
(Benutzername/Passwort), keine Identity Provider, kein 2FA.

Ablauf:
1. POST {base}/login/token.php            -> username, password, service=moodle_mobile_app
   Erfolg: {"token": ...}  ·  Fehler: {"error": ..., "errorcode": "invalidlogin"}
2. Verifikation: POST {base}/webservice/rest/server.php
   wstoken, wsfunction=core_webservice_get_site_info, moodlewsrestformat=json
   -> {"sitename", "username", "fullname", "userid", ...}  ·  {"exception": ..., "errorcode": "invalidtoken"}
3. Erst nach erfolgreicher Verifikation wird der Token gespeichert.
"""

from __future__ import annotations

import html
import re
import time
from typing import Any

from ..errors import (
    AuthError,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
)
from ..http import HttpClient, json_body, json_value
from ..models import (
    Course,
    Credentials,
    FileChild,
    FolderChild,
    LoginResult,
    LogoutResult,
    ModuleInfo,
    SectionInfo,
    SiteInfo,
    StatusResult,
    UrlChild,
)
from ..secrets import REDACTED
from ..session import SessionStore
from ..timeutil import semester_label, semester_sort_key, timestamp_to_iso
from .base import Backend

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SERVICE = "moodle_mobile_app"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"
ENROLLED_COURSES_FUNCTION = "core_enrol_get_users_courses"
COURSE_CONTENTS_FUNCTION = "core_course_get_contents"
REST_FORMAT = "json"

# Fehlercodes, die einen abgelehnten Login bedeuten (Moodle: login/token.php)
_AUTH_ERROR_CODES = {"invalidlogin", "invaliduser", "invalidaccount"}
_DENIED_ERROR_CODES = {"accessexception", "nopermission", "nopermtostore", "forbidden"}
# N2: Statusprüfung ist idempotent und darf einmal wiederholt werden
_SITE_INFO_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 0.5


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Entfernt Passwort/Token aus Servertexten (A1/A4)."""
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


class MoodleBackend(Backend):
    name = "moodle"
    supports_login = True

    def __init__(self, instance) -> None:
        super().__init__(instance)
        self.store = SessionStore(instance.key, instance.lms, instance.base_url)

    # -- Operationen ----------------------------------------------------
    def login(self, credentials: Credentials) -> LoginResult:
        with HttpClient(self.base_url) as client:
            token = self._request_token(client, credentials)
            info = self._site_info(client, token, label="Verifikation des Webservice")
        # erst nach erfolgreicher Verifikation wird der Token gespeichert
        self.store.save(token, username=info.username or credentials.username)
        return LoginResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            base_url=self.base_url,
            username=info.username or credentials.username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            verified=True,
            token_stored=True,
        )

    def status(self) -> StatusResult:
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        try:
            with HttpClient(self.base_url) as client:
                info = self._site_info(client, session.token, label="Statusprüfung")
        except SessionExpiredError:
            self.store.delete()
            raise
        return StatusResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            base_url=self.base_url,
            username=info.username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            logged_in=True,
        )

    def logout(self) -> LogoutResult:
        removed = self.store.delete()
        return LogoutResult(instance=self.instance.key, lms=self.instance.lms, token_removed=removed)

    # -- F2/F3: Kurse und Inhalte ---------------------------------------
    def courses(self) -> list[Course]:
        """Eigene Kurse: gespeicherter Token -> site_info (userid) -> enrolled courses."""
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        token = session.token
        try:
            with HttpClient(self.base_url) as client:
                info = self._site_info(client, token, label="Kursliste")
                if info.userid is None:
                    raise ParseError("Kursliste: Antwort enthält keine User-ID.")
                raw = self._rest_list(
                    client,
                    token,
                    ENROLLED_COURSES_FUNCTION,
                    {"userid": str(info.userid)},
                    label="Kursliste",
                )
        except SessionExpiredError:
            self.store.delete()
            raise
        parsed = [self._parse_course(entry) for entry in raw]
        parsed = [c for c in parsed if c is not None]
        # Sortierung: neuestes Semester zuerst, ohne Semester ans Ende, dann fullname (A–Z).
        with_sem = [c for c in parsed if c.semester]
        without = [c for c in parsed if not c.semester]
        with_sem.sort(key=lambda c: (-_semester_rank(c.semester), c.fullname.lower()))
        without.sort(key=lambda c: c.fullname.lower())
        return with_sem + without

    def course_contents(self, course_id: int) -> list[SectionInfo]:
        """Abschnitte eines Kurses via `core_course_get_contents`."""
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        token = session.token
        try:
            with HttpClient(self.base_url) as client:
                raw = self._rest_list(
                    client,
                    token,
                    COURSE_CONTENTS_FUNCTION,
                    {"courseid": str(course_id)},
                    label="Kursinhalt",
                )
        except SessionExpiredError:
            self.store.delete()
            raise
        sections: list[SectionInfo] = []
        for entry in raw:
            if isinstance(entry, dict):
                sections.append(parse_section(entry))
        sections.sort(key=lambda s: (s.number, s.id))
        return sections

    # -- Moodle-spezifisch ----------------------------------------------
    def _request_token(self, client: HttpClient, credentials: Credentials) -> str:
        label = "Login (login/token.php)"
        password = credentials.password.reveal()
        response = client.post_form(
            TOKEN_PATH,
            {"username": credentials.username, "password": password, "service": SERVICE},
            label=label,
        )
        data = json_body(response, label=label)
        self._raise_for_error(data, label=label, secrets=(password,))
        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            raise ParseError(f"{label}: Antwort enthält kein Token.")
        return token.strip()

    def _site_info(self, client: HttpClient, token: str, *, label: str) -> SiteInfo:
        """core_webservice_get_site_info: prüft den Token und liefert Konto + Plattform."""
        payload = {
            "wstoken": token,
            "wsfunction": SITE_INFO_FUNCTION,
            "moodlewsrestformat": REST_FORMAT,
        }
        data: dict[str, Any] | None = None
        for attempt in range(_SITE_INFO_ATTEMPTS):
            try:
                response = client.post_form(REST_PATH, payload, label=label)
            except NetworkError:
                if attempt == _SITE_INFO_ATTEMPTS - 1:
                    raise
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            data = json_body(response, label=label)
            self._raise_for_error(data, label=label, secrets=(token,))
            break
        if data is None:  # pragma: no cover - die Schleife endet immer mit raise oder data
            raise ParseError(f"{label}: keine Antwort.")
        info = SiteInfo.from_moodle_json(data)
        if not (info.username or info.fullname or info.sitename):
            raise ParseError(f"{label}: Antwort enthält weder username noch fullname noch sitename.")
        return info

    def _raise_for_error(self, data: dict[str, Any], *, label: str, secrets: tuple[str, ...] = ()) -> None:
        """Moodle-Fehlerobjekte (errorcode/exception) auf unsere Fehler abbilden.

        `secrets` wird aus Servertexten entfernt (A1/A4): ein Server, der das
        Passwort oder den Token in einer Meldung zurückspiegelt, darf sie nicht
        bis in die CLI-Ausgabe durchschlagen.
        """
        errorcode = data.get("errorcode")
        error = data.get("error") or data.get("message") or data.get("exception")
        if not isinstance(errorcode, str) and not isinstance(error, str):
            return
        code = errorcode if isinstance(errorcode, str) else "unknown"
        detail = scrub(error if isinstance(error, str) else "", secrets)
        suffix = f": {detail}" if detail else ""
        if code == "invalidtoken":
            raise SessionExpiredError(
                f"{label}: Token ungültig oder abgelaufen (errorcode invalidtoken){suffix}.",
                hint="Erneut mit `ilias login` anmelden (kein automatischer Re-Login).",
            )
        if code in _AUTH_ERROR_CODES:
            raise AuthError(
                f"Anmeldung abgelehnt (errorcode {code}){suffix}.",
                hint="Benutzername oder Passwort prüfen.",
            )
        if code in _DENIED_ERROR_CODES:
            raise AuthError(
                f"{label}: Webservice verweigert (errorcode {code}){suffix}.",
                hint="Der Webservice 'moodle_mobile_app' muss auf der Moodle-Instanz aktiv sein.",
            )
        raise ParseError(f"{label}: unerwartete Moodle-Fehlermeldung '{code}'{suffix}.")

    def _rest_list(
        self,
        client: HttpClient,
        token: str,
        wsfunction: str,
        params: dict[str, str],
        *,
        label: str,
    ) -> list[Any]:
        """Generischer REST-Aufruf, der eine JSON-Liste erwartet (F2/F3).

        Der Token steht immer im POST-Body, nie in der URL. Fehlerobjekte
        (dict mit errorcode/exception) werden wie bei `_site_info` abgebildet.
        """
        payload = {
            "wstoken": token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": REST_FORMAT,
            **params,
        }
        response = client.post_form(REST_PATH, payload, label=label)
        data = json_value(response, label=label)
        if isinstance(data, dict):
            self._raise_for_error(data, label=label, secrets=(token,))
            raise ParseError(f"{label}: unerwartete Antwort (Objekt statt Liste).")
        if not isinstance(data, list):
            raise ParseError(f"{label}: JSON ist keine Liste (Typ {type(data).__name__}).")
        return data

    def _parse_course(self, entry: Any) -> Course | None:
        """Ein Kurseintrag -> Course (None bei unbrauchbarem Eintrag)."""
        if not isinstance(entry, dict):
            raise ParseError("Kursliste: Kurseintrag ist kein Objekt.")
        raw_id = entry.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int):
            raise ParseError("Kursliste: Kurseintrag ohne numerische 'id'.")
        fullname = entry.get("fullname")
        shortname = entry.get("shortname")
        if not isinstance(fullname, str) or not fullname:
            raise ParseError(f"Kursliste: Kurs {raw_id} ohne 'fullname'.")
        if not isinstance(shortname, str) or not shortname:
            raise ParseError(f"Kursliste: Kurs {raw_id} ohne 'shortname'.")
        category = entry.get("category")
        if isinstance(category, bool) or not isinstance(category, int):
            category = None
        startdate = entry.get("startdate")
        enddate = entry.get("enddate")
        visible_raw = entry.get("visible", 1)
        visible = True if visible_raw is None else bool(visible_raw)
        return Course(
            id=raw_id,
            fullname=fullname,
            shortname=shortname,
            category=category,
            semester=semester_label(startdate),
            visible=visible,
            startdate=timestamp_to_iso(startdate),
            enddate=timestamp_to_iso(enddate),
            url=f"{self.base_url}/course/view.php?id={raw_id}",
        )


# ------------------------------------------------------------------ F3-Helfer (rein, einzeln testbar)

def _semester_rank(semester: str | None) -> int:
    """Semester -> aufsteigende Rangzahl (größer = neuer), None -> kleinster."""
    year, term = semester_sort_key(semester)
    if year < 0:
        return -1
    return year * 10 + term


_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: object) -> str:
    """HTML-Tags entfernen, Entities auflösen, Whitespace falten."""
    if not isinstance(text, str) or not text:
        return ""
    cleaned = text.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def short_label(name: object, limit: int = 60) -> str:
    """Kurzer Klartext-Name für `label`-Module (max. 60 Zeichen)."""
    text = strip_html(name)
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _content_file(entry: dict[str, Any]) -> FileChild | None:
    filename = entry.get("filename")
    if not isinstance(filename, str) or not filename:
        return None
    filepath = entry.get("filepath")
    path = filepath if isinstance(filepath, str) and filepath.startswith("/") else "/"
    size = entry.get("filesize")
    if isinstance(size, bool) or not isinstance(size, int):
        size = None
    mimetype = entry.get("mimetype")
    if not isinstance(mimetype, str) or not mimetype:
        mimetype = None
    return FileChild(
        name=filename,
        path=path,
        size=size,
        mimetype=mimetype,
        timemodified=timestamp_to_iso(entry.get("timemodified")),
        fileurl=entry.get("fileurl") if isinstance(entry.get("fileurl"), str) else None,
    )


def build_folder_children(contents: list[Any]) -> tuple[Any, ...]:
    """`filepath`-Werte eines `folder`-Moduls -> verschachtelte Ordner/Dateien.

    "/a/b/c.pdf" erzeugt Ordner "a" -> Ordner "b" -> Datei "c.pdf".
    Dateien mit filepath "/" liegen direkt im Modul.
    """
    root: dict[str, Any] = {}  # Name -> {"name", "path", "folders", "folder_order", "files"}
    top_files: list[FileChild] = []

    def _get_or_create(node_map: dict[str, Any], name: str, path: str) -> dict[str, Any]:
        node = node_map.get(name)
        if node is None:
            node = {"name": name, "path": path, "folders": {}, "folder_order": [], "files": []}
            node_map[name] = node
        return node

    for entry in contents:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        file = _content_file(entry)
        if file is None:
            continue
        raw_path = file.path if file.path.startswith("/") else "/"
        parts = [p for p in raw_path.strip("/").split("/") if p]
        if not parts:
            top_files.append(file)
            continue
        node_map, prefix = root, ""
        node = None
        for part in parts:
            prefix = f"{prefix}/{part}"
            child = node_map.get(part)
            if child is None:
                child = {"name": part, "path": prefix + "/", "folders": {}, "files": []}
                node_map[part] = child
            node = child
            node_map = child["folders"]
        assert node is not None
        node["files"].append(file)

    folders: list[Any] = []
    for name, node in root.items():
        children: list[Any] = [_freeze_one(sub) for sub in node["folders"].values()]
        children.extend(node["files"])
        folders.append(FolderChild(name=name, path=node["path"], children=tuple(children)))
    folders.extend(top_files)
    return tuple(folders)


def _freeze_one(node: dict[str, Any]) -> FolderChild:
    children: list[Any] = [_freeze_one(sub) for sub in node["folders"].values()]
    children.extend(node["files"])
    return FolderChild(name=node["name"], path=node["path"], children=tuple(children))


def parse_module(entry: dict[str, Any]) -> ModuleInfo:
    """Ein Modul aus `core_course_get_contents` -> ModuleInfo mit Kindern."""
    raw_id = entry.get("id")
    mod_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else 0
    modname = entry.get("modname") if isinstance(entry.get("modname"), str) else ""
    raw_name = entry.get("name") if isinstance(entry.get("name"), str) else ""
    name = short_label(raw_name) if modname == "label" else strip_html(raw_name) or raw_name
    url = entry.get("url") if isinstance(entry.get("url"), str) else None
    visible = _as_bool(entry.get("visible", 1))
    uservisible = _as_bool(entry.get("uservisible", True))
    availability = strip_html(entry.get("availabilityinfo")) or None
    contents = entry.get("contents")
    if not isinstance(contents, list):
        contents = []
    children: list[Any] = []
    if modname == "folder":
        children = list(build_folder_children(contents))
    elif modname == "resource":
        for item in contents:
            if isinstance(item, dict) and item.get("type") == "file":
                file = _content_file(item)
                if file is not None:
                    children.append(file)
    elif modname == "url":
        for item in contents:
            if isinstance(item, dict) and item.get("type") == "url":
                target = item.get("fileurl")
                label = item.get("filename") if isinstance(item.get("filename"), str) else raw_name
                if isinstance(target, str) and target:
                    children.append(UrlChild(name=strip_html(label) or label, url=target))
        if not children and url:
            children.append(UrlChild(name=name, url=url))
    return ModuleInfo(
        id=mod_id,
        name=name,
        modname=modname,
        url=url,
        visible=visible,
        uservisible=uservisible,
        availability=availability,
        children=tuple(children),
    )


def parse_section(entry: dict[str, Any]) -> SectionInfo:
    """Ein Abschnitt aus `core_course_get_contents` -> SectionInfo."""
    raw_id = entry.get("id")
    sec_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else 0
    raw_num = entry.get("section")
    number = raw_num if isinstance(raw_num, int) and not isinstance(raw_num, bool) else 0
    name = entry.get("name") if isinstance(entry.get("name"), str) else ""
    modules_raw = entry.get("modules")
    if not isinstance(modules_raw, list):
        modules_raw = []
    modules = tuple(parse_module(m) for m in modules_raw if isinstance(m, dict))
    return SectionInfo(
        id=sec_id,
        number=number,
        name=name,
        visible=_as_bool(entry.get("visible", 1)),
        uservisible=_as_bool(entry.get("uservisible", True)),
        modules=modules,
    )
