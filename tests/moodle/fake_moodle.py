"""Lokaler Fake-Moodle-Server (nur stdlib, nur 127.0.0.1).

Bildet die Endpunkte nach, die der Login-Teil und F2/F3 benutzen
(siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):

  POST /login/token.php              username, password, service=moodle_mobile_app
        -> {"token": ..., "privatetoken": null}
        -> {"error": "Invalid login, please try again", "errorcode": "invalidlogin"}
  POST /webservice/rest/server.php   wstoken, wsfunction, moodlewsrestformat
        -> core_webservice_get_site_info: {"sitename", "username", "fullname", "userid", ...}
        -> core_enrol_get_users_courses: [{"id", "shortname", "fullname", "startdate", ...}, ...]
        -> core_course_get_contents:     [{"id", "section", "modules": [...]}, ...]
        -> {"exception": "moodle_exception", "errorcode": "invalidtoken", ...}

Schalter für Fehlerszenarien: token_mode, rest_mode (global), courses_mode und
contents_mode pro Funktion (siehe FakeMoodle). Der Token wird immer im POST-Body
geprüft und nie in einer URL erwartet.
"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .fixtures import CONTENTS, COURSES, UNKNOWN_COURSE

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"
COURSES_FUNCTION = "core_enrol_get_users_courses"
CONTENTS_FUNCTION = "core_course_get_contents"
SITE_NAME = "Lernplattform TH-MA"

MAINTENANCE_HTML = """<!DOCTYPE html><html lang="de"><head><title>Wartung | moodle</title></head>
<body><h1>Wartungsarbeiten</h1><p>Der Moodle-Dienst ist vorübergehend nicht verfügbar.</p></body></html>"""

LOGIN_PAGE_HTML = """<!DOCTYPE html><html lang="de"><head><title>Anmeldeseite | moodle</title></head>
<body><form class="login-form" action="https://moodle.hs-mannheim.de/login/index.php" method="post" id="login">
<input type="hidden" name="logintoken" value="REDACTED">
<input type="text" name="username" id="username"><input type="password" name="password">
<button type="submit">Anmelden</button></form></body></html>"""

# Modi pro REST-Funktion: normal | server_error | html | invalid_token
# | access_denied | broken (Pflichtfelder fehlen) | object (Objekt statt Liste)


def expand(value: Any, base_url: str) -> Any:
    """`{base}` in den Fixtures durch die Basis-URL des Fake-Servers ersetzen."""
    if isinstance(value, str):
        return value.replace("{base}", base_url)
    if isinstance(value, list):
        return [expand(item, base_url) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, base_url) for key, item in value.items()}
    return value


@dataclass
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    form: dict[str, list[str]]
    headers: dict[str, str]

    def form_value(self, key: str) -> str | None:
        values = self.form.get(key)
        return values[0] if values else None

    def query_value(self, key: str) -> str | None:
        values = self.query.get(key)
        return values[0] if values else None

    @property
    def wsfunction(self) -> str | None:
        return self.form_value("wsfunction")


@dataclass
class FakeMoodle:
    username: str
    password: str
    sitename: str = SITE_NAME
    fullname: str = "Erika Musterfrau"
    userid: int = 4711
    # token_mode: normal | server_error | html | empty | access_denied | echo_password
    token_mode: str = "normal"
    # rest_mode: global für alle REST-Funktionen
    # normal | invalid_token | server_error | html | echo_token
    rest_mode: str = "normal"
    # courses_mode / contents_mode: siehe _ERROR_MODES oben
    courses_mode: str = "normal"
    contents_mode: str = "normal"
    courses: list[dict] = field(default_factory=lambda: [dict(c) for c in COURSES])
    contents: dict[int, list[dict]] = field(default_factory=lambda: {k: [dict(s) for s in v] for k, v in CONTENTS.items()})
    tokens: dict[str, str] = field(default_factory=dict)  # token -> username
    requests: list[RecordedRequest] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    port: int = 0
    _server: ThreadingHTTPServer | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # -- Lebenszyklus ----------------------------------------------------
    def start(self) -> FakeMoodle:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # -- Helfer für Tests -------------------------------------------------
    def expire_tokens(self) -> None:
        """Alle Token entwerten (simuliert abgelaufene Session)."""
        with self.lock:
            self.tokens.clear()

    def issue_token(self, username: str | None = None) -> str:
        token = "tok-" + secrets.token_hex(12)
        with self.lock:
            self.tokens[token] = username or self.username
        return token

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.path == path]

    def calls_to(self, function: str) -> list[RecordedRequest]:
        return [r for r in self.requests_to(REST_PATH) if r.wsfunction == function]

    def last_token_php(self) -> RecordedRequest | None:
        found = self.requests_to(TOKEN_PATH)
        return found[-1] if found else None

    def last_rest(self) -> RecordedRequest | None:
        found = self.requests_to(REST_PATH)
        return found[-1] if found else None


def _make_handler(world: FakeMoodle):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # still
            pass

        # -- infra --
        def _record(self, body: bytes) -> RecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            form: dict[str, list[str]] = {}
            if "form-urlencoded" in self.headers.get("Content-Type", ""):
                form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            rec = RecordedRequest(
                method=self.command,
                path=parsed.path,
                query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                form=form,
                headers={k: v for k, v in self.headers.items()},
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send_json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload))

        def _send_html(self, status: int, html: str, ctype: str = "text/html; charset=UTF-8") -> None:
            self._send(status, html, ctype)

        def _send(self, status: int, body: str, ctype: str = "application/json; charset=UTF-8") -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_GET(self):
            self._record(b"")
            if self.path.split("?")[0] == "/login/index.php":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            return self._send(404, json.dumps({"error": "notfound", "errorcode": "notfound"}))

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)
            if rec.path == TOKEN_PATH:
                return self._token(rec)
            if rec.path == REST_PATH:
                return self._rest(rec)
            return self._send(404, json.dumps({"error": "notfound", "errorcode": "notfound"}))

        # -- Endpunkte --
        def _token(self, rec: RecordedRequest) -> None:
            if world.token_mode == "server_error":
                return self._send_html(503, "<h1>503 Service Unavailable</h1>", "text/html; charset=UTF-8")
            if world.token_mode == "html":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            if world.token_mode == "empty":
                return self._send_json(200, {"privatetoken": None})
            if world.token_mode == "echo_password":
                # bösartiger/fehlerhafter Server, der das Passwort in der Meldung zurückspiegelt
                return self._send_json(
                    200,
                    {
                        "error": f"Login for {rec.form_value('username')} with password "
                        f"{rec.form_value('password')} failed",
                        "errorcode": "invalidlogin",
                    },
                )
            if world.token_mode == "access_denied":
                return self._send_json(
                    403,
                    {
                        "error": "Web service is disabled",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            if rec.form_value("username") != world.username or rec.form_value("password") != world.password:
                return self._send_json(
                    200, {"error": "Invalid login, please try again", "errorcode": "invalidlogin"}
                )
            token = world.issue_token(world.username)
            return self._send_json(200, {"token": token, "privatetoken": None})

        def _rest(self, rec: RecordedRequest) -> None:
            if world.rest_mode == "server_error":
                return self._send_html(502, "<h1>502 Bad Gateway</h1>", "text/html; charset=UTF-8")
            if world.rest_mode == "html":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            token = rec.form_value("wstoken") or ""
            function = rec.form_value("wsfunction") or ""
            fmt = rec.form_value("moodlewsrestformat") or ""
            if function not in {
                SITE_INFO_FUNCTION,
                COURSES_FUNCTION,
                CONTENTS_FUNCTION,
            } or fmt != "json":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            if world.rest_mode == "echo_token":
                return self._send_json(
                    401,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": f"Invalid token: {token}",
                    },
                )
            with world.lock:
                username = world.tokens.get(token)
            if world.rest_mode == "invalid_token" or username is None:
                return self._send_json(
                    401,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                        "debuginfo": "Token was not found in the database",
                    },
                )
            if function == SITE_INFO_FUNCTION:
                return self._site_info(username)
            if function == COURSES_FUNCTION:
                return self._courses(rec)
            return self._contents(rec)

        def _mode_switch(self, mode: str) -> bool:
            """Fehlerantworten der Modi; True = Antwort gesendet."""
            if mode == "server_error":
                self._send_html(503, "<h1>503 Service Unavailable</h1>", "text/html; charset=UTF-8")
            elif mode == "html":
                self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            elif mode == "invalid_token":
                self._send_json(
                    401,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    },
                )
            elif mode == "access_denied":
                self._send_json(
                    403,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            elif mode == "broken":
                # Antwort ohne die erwarteten Pflichtfelder
                self._send_json(200, [{"shortname": "OHNE-ID", "fullname": "Kurs ohne ID"}])
            elif mode == "object":
                self._send_json(200, {"unexpected": "object"})
            else:
                return False
            return True

        def _site_info(self, username: str) -> None:
            return self._send_json(
                200,
                {
                    "sitename": world.sitename,
                    "username": username,
                    "fullname": world.fullname,
                    "userid": world.userid,
                    "siteurl": world.base_url,
                    "release": "4.5 (Build: 20250210)",
                    "version": "2025021000",
                    "lang": "de",
                    "siteid": 1,
                },
            )

        def _courses(self, rec: RecordedRequest) -> None:
            """core_enrol_get_users_courses: erwartet die userid im POST-Body."""
            if self._mode_switch(world.courses_mode):
                return
            if rec.form_value("userid") != str(world.userid):
                return self._send_json(
                    200,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidparameter",
                        "message": "Invalid parameter value detected for userid",
                    },
                )
            with world.lock:
                payload = [expand(dict(course), world.base_url) for course in world.courses]
            return self._send_json(200, payload)

        def _contents(self, rec: RecordedRequest) -> None:
            """core_course_get_contents: erwartet die courseid im POST-Body."""
            if self._mode_switch(world.contents_mode):
                return
            courseid = rec.form_value("courseid") or ""
            with world.lock:
                sections = world.contents.get(int(courseid)) if courseid.isdigit() else None
                payload = [expand(dict(section), world.base_url) for section in sections] if sections else None
            if payload is None:
                return self._send_json(200, UNKNOWN_COURSE)
            return self._send_json(200, payload)

    return Handler
