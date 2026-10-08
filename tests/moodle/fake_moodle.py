"""Lokaler Fake-Moodle-Server (nur stdlib, nur 127.0.0.1).

Bildet genau die zwei Endpunkte nach, die der Login-Teil benutzt
(siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):

  POST /login/token.php              username, password, service=moodle_mobile_app
        -> {"token": ..., "privatetoken": null}
        -> {"error": "Invalid login, please try again", "errorcode": "invalidlogin"}
  POST /webservice/rest/server.php   wstoken, wsfunction, moodlewsrestformat
        -> {"sitename", "username", "fullname", "userid", ...}
        -> {"exception": "moodle_exception", "errorcode": "invalidtoken", ...}

Schalter für Fehlerszenarien: token_mode, rest_mode (siehe FakeMoodle).

Erweitert für F2/F3:
  wsfunction=core_enrol_get_users_courses  -> Liste von Kursen
  wsfunction=core_course_get_contents      -> Kursinhalt (Abschnitte, Module, Dateien)
"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SITE_NAME = "Lernplattform TH-MA"

MAINTENANCE_HTML = """<!DOCTYPE html><html lang="de"><head><title>Wartung | moodle</title></head>
<body><h1>Wartungsarbeiten</h1><p>Der Moodle-Dienst ist vorübergehend nicht verfügbar.</p></body></html>"""

LOGIN_PAGE_HTML = """<!DOCTYPE html><html lang="de"><head><title>Anmeldeseite | moodle</title></head>
<body><form class="login-form" action="https://moodle.hs-mannheim.de/login/index.php" method="post" id="login">
<input type="hidden" name="logintoken" value="REDACTED">
<input type="text" name="username" id="username"><input type="password" name="password">
<button type="submit">Anmelden</button></form></body></html>"""


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


@dataclass
class FakeMoodle:
    username: str
    password: str
    sitename: str = SITE_NAME
    fullname: str = "Erika Musterfrau"
    userid: int = 4711
    # token_mode: normal | server_error | html | empty | access_denied | echo_password
    token_mode: str = "normal"
    # rest_mode: normal | invalid_token | server_error | html | echo_token
    rest_mode: str = "normal"
    tokens: dict[str, str] = field(default_factory=dict)  # token -> username
    requests: list[RecordedRequest] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Fixtures für F2/F3
    courses_fixture: list[dict] | None = None
    course_contents_fixture: dict[int, list] | None = None

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
            
            # Token prüfen (außer bei echo_token Mode)
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
            
            # Funktionen verteilen
            if function == "core_webservice_get_site_info":
                return self._handle_site_info(username)
            elif function == "core_enrol_get_users_courses":
                return self._handle_users_courses(username)
            elif function == "core_course_get_contents":
                return self._handle_course_contents(rec)
            else:
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
        
        def _handle_site_info(self, username: str) -> None:
            self._send_json(
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
        
        def _handle_users_courses(self, username: str) -> None:
            courses = world.courses_fixture
            if courses is None:
                courses = _default_courses_fixture(username, world.userid)
            self._send_json(200, courses)
        
        def _handle_course_contents(self, rec: RecordedRequest) -> None:
            courseid_str = rec.form_value("courseid") or ""
            try:
                courseid = int(courseid_str)
            except ValueError:
                self._send_json(200, {"exception": "invalid_parameter_exception", "errorcode": "invalidparameter", "message": "Invalid courseid"})
                return
            
            contents = None
            if world.course_contents_fixture is not None:
                contents = world.course_contents_fixture.get(courseid)
            if contents is None:
                contents = _default_course_contents_fixture(courseid)
            self._send_json(200, contents)

    return Handler
