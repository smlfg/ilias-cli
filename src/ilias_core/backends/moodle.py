"""Moodle-Backend: Login/Status/Logout und die Lese-Operationen courses/ls.

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

Kurse (F2) und Kursinhalt (F3) nutzen denselben REST-Endpunkt; der Token steht
immer nur im POST-Body, nie in der URL:

4. wsfunction=core_enrol_get_users_courses, userid=<userid aus Schritt 2> -> [Kurs, ...]
5. wsfunction=core_course_get_contents, courseid=<id> -> [Abschnitt, ...]

Die Antworten dieser Funktionen sind JSON-Listen; Fehler kommen als Objekt mit
`exception`/`errorcode`.
"""

from __future__ import annotations

import time
from typing import Any

from ..courses import nest_files, sort_courses
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
    CourseListResult,
    Credentials,
    FileNode,
    LoginResult,
    LogoutResult,
    ModuleNode,
    SectionNode,
    SiteInfo,
    StatusResult,
    UrlNode,
    as_bool,
    as_int,
)
from ..secrets import REDACTED
from ..session import SessionStore, StoredSession
from ..text import label as short_label
from ..text import plain_text
from ..timeutil import iso_or_none
from .base import Backend

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SERVICE = "moodle_mobile_app"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"
COURSES_FUNCTION = "core_enrol_get_users_courses"
CONTENTS_FUNCTION = "core_course_get_contents"
REST_FORMAT = "json"

# Modultypen, deren Inhalte als Baum ausgegeben werden (alles andere ist ein Blatt)
EXPANDED_MODULES = frozenset({"folder", "resource", "url"})
LABEL_LIMIT = 60

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
        session = self._require_session()
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

    # -- F2/F3: eigene Kurse und Kursinhalt ---------------------------
    def courses(self) -> CourseListResult:
        """F2: `core_enrol_get_users_courses` für die eigene userid."""
        session = self._require_session()
        label = f"Kursliste ({COURSES_FUNCTION})"
        with HttpClient(self.base_url) as client:
            info = self._site_info(client, session.token, label="User-ID (core_webservice_get_site_info)")
            if info.userid is None:
                raise ParseError(
                    "core_webservice_get_site_info: Antwort enthält keine userid.",
                    hint="Ohne userid lässt sich die Kursliste nicht abrufen.",
                )
            raw = self._call_list(client, session.token, COURSES_FUNCTION, {"userid": str(info.userid)}, label=label)
        courses: list[Course] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ParseError(f"{label}: unerwarteter Eintrag (Typ {type(entry).__name__}).")
            courses.append(Course.from_moodle_json(entry, base_url=self.base_url))
        return CourseListResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            courses=sort_courses(courses),
        )

    def course_contents(self, course_id: int) -> tuple[SectionNode, ...]:
        """F3: `core_course_get_contents` -> Abschnitte -> Module -> Dateien/Ordner."""
        session = self._require_session()
        label = f"Kursinhalt ({CONTENTS_FUNCTION})"
        with HttpClient(self.base_url) as client:
            raw = self._call_list(client, session.token, CONTENTS_FUNCTION, {"courseid": str(course_id)}, label=label)
        sections: list[SectionNode] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ParseError(f"{label}: unerwarteter Abschnitt (Typ {type(entry).__name__}).")
            sections.append(self._section(entry, label=label))
        return tuple(sections)

    # -- interne Helfer --------------------------------------------------
    def _require_session(self) -> StoredSession:
        """Token aus dem Session-Speicher - sonst Exit 2 (nicht eingeloggt)."""
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        return session

    def _call_list(
        self,
        client: HttpClient,
        token: str,
        function: str,
        params: dict[str, str],
        *,
        label: str,
    ) -> list[Any]:
        """REST-Aufruf, dessen Antwort eine JSON-Liste ist; Fehlerobjekte -> Fehler."""
        payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": REST_FORMAT}
        payload.update(params)
        response = client.post_form(REST_PATH, payload, label=label)
        data = json_value(response, label=label)
        if isinstance(data, dict):
            # Moodle meldet Fehler als Objekt; alles andere wäre unerwartet.
            self._raise_for_error(data, label=label, secrets=(token,))
            raise ParseError(f"{label}: unerwartetes JSON-Objekt statt einer Liste.")
        if not isinstance(data, list):
            raise ParseError(f"{label}: JSON ist keine Liste (Typ {type(data).__name__}).")
        return data

    def _section(self, data: dict[str, Any], *, label: str) -> SectionNode:
        section_id = data.get("id")
        if not isinstance(section_id, int) or isinstance(section_id, bool):
            raise ParseError(f"{label}: Abschnitt ohne gültige 'id'.")
        modules: list[ModuleNode] = []
        for entry in data.get("modules") or []:
            if not isinstance(entry, dict):
                raise ParseError(f"{label}: unerwartetes Modul (Typ {type(entry).__name__}).")
            modules.append(self._module(entry, label=label))
        return SectionNode(
            id=section_id,
            number=as_int(data.get("section")) or 0,
            name=plain_text(data.get("name")),
            visible=as_bool(data.get("visible"), default=True),
            uservisible=as_bool(data.get("uservisible"), default=True),
            modules=tuple(modules),
        )

    def _module(self, data: dict[str, Any], *, label: str) -> ModuleNode:
        module_id = data.get("id")
        if not isinstance(module_id, int) or isinstance(module_id, bool):
            raise ParseError(f"{label}: Modul ohne gültige 'id'.")
        modname = str(data.get("modname") or "").strip().lower()
        raw_name = data.get("name")
        # `label`-Module tragen ihren Text im Namen (HTML) - als Kurztext anzeigen.
        name = (
            short_label(raw_name, limit=LABEL_LIMIT, fallback="Beschriftung")
            if modname == "label"
            else plain_text(raw_name) or f"Modul {module_id}"
        )
        return ModuleNode(
            id=module_id,
            name=name,
            modname=modname,
            url=plain_text(data.get("url")) or None,
            visible=as_bool(data.get("visible"), default=True),
            uservisible=as_bool(data.get("uservisible"), default=True),
            availability=plain_text(data.get("availabilityinfo")) or None,
            children=self._children(data, modname=modname, label=label),
        )

    def _children(self, data: dict[str, Any], *, modname: str, label: str) -> tuple[Any, ...]:
        """Inhalte eines Moduls; nur `folder`/`resource`/`url` werden ausgeklappt."""
        contents = data.get("contents")
        if modname not in EXPANDED_MODULES or not isinstance(contents, list) or not contents:
            return ()
        files: list[FileNode] = []
        links: list[UrlNode] = []
        for entry in contents:
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("type") or "").strip().lower()
            filename = plain_text(entry.get("filename"))
            url = plain_text(entry.get("fileurl"))
            if kind == "url" or (modname == "url" and url):
                if url:
                    links.append(UrlNode(name=filename or data.get("name") or url, url=url))
            elif kind in {"file", "html"} or modname == "resource":
                if not filename and not url:
                    continue
                files.append(
                    FileNode(
                        name=filename or url or "Datei",
                        path=plain_text(entry.get("filepath")) or "/",
                        size=as_int(entry.get("filesize")),
                        mimetype=plain_text(entry.get("mimetype")) or None,
                        timemodified=iso_or_none(entry.get("timemodified")),
                        fileurl=url or None,
                    )
                )
        if modname == "folder":
            # `filepath` wird zu verschachtelten Ordnern
            return nest_files(files) + tuple(links)
        return tuple(files + links)

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
