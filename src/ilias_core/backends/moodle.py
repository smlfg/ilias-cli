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

import time
from typing import Any

from ..errors import (
    AuthError,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
)
from ..http import HttpClient, json_body
from ..models import (
    Course,
    CourseContentsResult,
    CourseSection,
    CoursesResult,
    Credentials,
    LoginResult,
    LogoutResult,
    SiteInfo,
    StatusResult,
)
from ..secrets import REDACTED
from ..session import SessionStore
from .base import Backend

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SERVICE = "moodle_mobile_app"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"
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

    # -- F2: Kurse auflisten ---------------------------------------------
    def courses(self) -> CoursesResult:
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        with HttpClient(self.base_url) as client:
            # Erst userid über site_info ermitteln
            info = self._site_info(client, session.token, label="Site-Info für User-ID")
            if info.userid is None:
                raise ParseError("Site-Info liefert keine User-ID.")
            # Dann Kurse abrufen
            courses = self._get_users_courses(client, session.token, info.userid)
        return CoursesResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            count=len(courses),
            courses=tuple(courses),
        )

    def _get_users_courses(self, client: HttpClient, token: str, userid: int) -> list[Course]:
        """core_enrol_get_users_courses: liefert die Kurse eines Nutzers."""
        payload = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_users_courses",
            "moodlewsrestformat": REST_FORMAT,
            "userid": str(userid),
        }
        label = "Kursliste abrufen"
        response = client.post_form(REST_PATH, payload, label=label)
        data = json_body(response, label=label)
        self._raise_for_error(data, label=label, secrets=(token,))
        if not isinstance(data, list):
            raise ParseError(f"{label}: Antwort ist keine Liste.")
        courses = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                courses.append(Course.from_moodle_json(item, self.base_url))
            except Exception:
                # Kaputte Kurs-Einträge überspringen
                pass
        # Sortieren: nach Semester (neueste zuerst, None am Ende), dann fullname
        def sort_key(c: Course):
            sem = c.semester or ""
            # Semester-String für Sortierung: "WiSe 2026/27" > "SoSe 2026" > ""
            # Wir parsen das Semester grob für Sortierung
            return (sem == "", sem, c.fullname.lower())
        courses.sort(key=sort_key, reverse=True)
        return courses

    # -- F3: Kursinhalt als Baum -----------------------------------------
    def course_contents(self, course_id: int) -> CourseContentsResult:
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        with HttpClient(self.base_url) as client:
            sections = self._get_course_contents(client, session.token, course_id)
        # Kurs-Info für das Ergebnis (wir haben sie aus der Kursliste oder holen sie separat)
        # Für simplicity: wir nutzen eine minimale Info, da der Kurs schon aufgelöst wurde
        course_info = {"id": course_id, "fullname": "", "shortname": ""}
        return CourseContentsResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            course=course_info,
            depth=None,  # wird im Service gesetzt
            sections=tuple(sections),
        )

    def _get_course_contents(self, client: HttpClient, token: str, course_id: int) -> list:
        """core_course_get_contents: liefert Abschnitte mit Modulen und Dateien."""
        payload = {
            "wstoken": token,
            "wsfunction": "core_course_get_contents",
            "moodlewsrestformat": REST_FORMAT,
            "courseid": str(course_id),
        }
        label = "Kursinhalt abrufen"
        response = client.post_form(REST_PATH, payload, label=label)
        data = json_body(response, label=label)
        self._raise_for_error(data, label=label, secrets=(token,))
        if not isinstance(data, list):
            raise ParseError(f"{label}: Antwort ist keine Liste.")
        sections = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                sections.append(CourseSection.from_moodle_json(item))
            except Exception:
                # Kaputte Abschnitt-Einträge überspringen
                pass
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
