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

# Realistische Fixtures (Moodle 4.x-Form). Zeitstempel in Europe/Berlin:
# 1774994400 = 2026-04-01 (SoSe 2026), 1790805600 = 2026-10-01 (WiSe 2026/27).
COURSES: list[dict] = [
    {
        "id": 101,
        "shortname": "PR1-WS26",
        "fullname": "Programmieren 1 (WS 2026/27)",
        "displayname": "Programmieren 1",
        "enrolledusercount": 120,
        "idnumber": "",
        "visible": 1,
        "summary": "<p>Einführung in die Programmierung</p>",
        "summaryformat": 1,
        "format": "topics",
        "category": 17,
        "progress": None,
        "completed": False,
        "startdate": 1790805600,
        "enddate": 1806357600,
        "lastaccess": 1791000000,
        "isfavourite": False,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": 1790000000,
    },
    {
        "id": 102,
        "shortname": "MA1-SS26",
        "fullname": "Mathematik für Ingenieure (SoSe 2026)",
        "visible": 1,
        "category": 18,
        "startdate": 1774994400,
        "enddate": 1790805600,
        "timemodified": 1774000000,
    },
    {
        "id": 103,
        "shortname": "MA2-WS26",
        "fullname": "Mathematik 2 (WS 2026/27)",
        "visible": 1,
        "category": 18,
        "startdate": 1790805600,
        "enddate": 1806357600,
        "timemodified": 1790000000,
    },
    {
        "id": 104,
        "shortname": "ALT-000",
        "fullname": "Altdatenbank (ohne Startdatum)",
        "visible": 1,
        "startdate": 0,
        "enddate": 0,
        "timemodified": 1600000000,
    },
    {
        "id": 105,
        "shortname": "HID-1",
        "fullname": "Versteckter Kurs",
        "visible": 0,
        "category": 19,
        "startdate": 1790805600,
        "enddate": 1806357600,
        "timemodified": 1790000000,
    },
]


def _file(filename, filepath, filesize, fileurl, timemodified, mimetype):
    return {
        "type": "file",
        "filename": filename,
        "filepath": filepath,
        "filesize": filesize,
        "fileurl": fileurl,
        "timecreated": timemodified,
        "timemodified": timemodified,
        "sortorder": 0,
        "mimetype": mimetype,
        "isexternalfile": False,
        "userid": 55,
        "author": "Prof. X",
        "license": "allrightsreserved",
    }


COURSE_CONTENTS: dict[int, list[dict]] = {
    101: [
        {
            "id": 501,
            "name": "Allgemeines",
            "visible": 1,
            "summary": "",
            "summaryformat": 1,
            "section": 0,
            "hiddenbynumsections": 0,
            "uservisible": True,
            "modules": [
                {
                    "id": 9001,
                    "url": "https://moodle.hs-mannheim.de/mod/folder/view.php?id=9001",
                    "name": "Übungsblätter",
                    "instance": 33,
                    "contextid": 777,
                    "visible": 1,
                    "uservisible": True,
                    "visibleoncoursepage": 1,
                    "modicon": "folder",
                    "modname": "folder",
                    "modplural": "Verzeichnisse",
                    "indent": 0,
                    "noviewlink": False,
                    "completion": 0,
                    "contents": [
                        _file(
                            "blatt01.pdf",
                            "/",
                            183456,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/777/mod_folder/content/0/blatt01.pdf?forcedownload=1",
                            1790900000,
                            "application/pdf",
                        ),
                        _file(
                            "blatt02.pdf",
                            "/Blatt 2/",
                            204800,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/777/mod_folder/content/0/Blatt%202/blatt02.pdf?forcedownload=1",
                            1790910000,
                            "application/pdf",
                        ),
                        _file(
                            "aufgabe1.pdf",
                            "/Blatt 1/",
                            51200,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/777/mod_folder/content/0/Blatt%201/aufgabe1.pdf?forcedownload=1",
                            1790920000,
                            "application/pdf",
                        ),
                        _file(
                            "loesung1.md",
                            "/Blatt 1/Lösungen/",
                            4096,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/777/mod_folder/content/0/Blatt%201/L%C3%B6sungen/loesung1.md?forcedownload=1",
                            1790930000,
                            "text/markdown",
                        ),
                    ],
                    "contentsinfo": {"filescount": 4, "filessize": 444552},
                },
                {
                    "id": 9002,
                    "url": "https://moodle.hs-mannheim.de/mod/url/view.php?id=9002",
                    "name": "Moodle-Doku",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "url",
                    "modplural": "Links",
                    "contents": [
                        {
                            "type": "url",
                            "filename": "Moodle-Doku",
                            "filepath": "/",
                            "filesize": 0,
                            "fileurl": "https://docs.moodle.org/",
                            "timemodified": 1790800000,
                            "mimetype": "text/html",
                        }
                    ],
                },
                {
                    "id": 9003,
                    "url": "https://moodle.hs-mannheim.de/mod/label/view.php?id=9003",
                    "name": "Willkommen im Kurs <p>Bitte <strong>alles</strong> lesen</p>",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "label",
                    "modplural": "Textfelder",
                },
            ],
        },
        {
            "id": 502,
            "name": "Übung 1",
            "visible": 1,
            "section": 1,
            "uservisible": True,
            "modules": [
                {
                    "id": 9010,
                    "url": "https://moodle.hs-mannheim.de/mod/resource/view.php?id=9010",
                    "name": "Skript Kapitel 1",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "resource",
                    "modplural": "Dateien",
                    "contents": [
                        _file(
                            "kapitel1.pdf",
                            "/",
                            1048576,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/778/mod_resource/content/0/kapitel1.pdf?forcedownload=1",
                            1791000000,
                            "application/pdf",
                        )
                    ],
                },
                {
                    "id": 9011,
                    "url": "https://moodle.hs-mannheim.de/mod/assign/view.php?id=9011",
                    "name": "Aufgabe 1",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "assign",
                    "modplural": "Aufgaben",
                },
                {
                    "id": 9012,
                    "url": "https://moodle.hs-mannheim.de/mod/forum/view.php?id=9012",
                    "name": "Fragenforum",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "forum",
                    "modplural": "Foren",
                },
            ],
        },
        {
            "id": 503,
            "name": "",
            "visible": 1,
            "section": 2,
            "uservisible": True,
            "modules": [],
        },
        {
            "id": 504,
            "name": "Altklausuren",
            "visible": 1,
            "section": 3,
            "uservisible": True,
            "modules": [
                {
                    "id": 9020,
                    "url": "https://moodle.hs-mannheim.de/mod/folder/view.php?id=9020",
                    "name": "[Klausur] Altklausuren",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "folder",
                    "modplural": "Verzeichnisse",
                    "contents": [
                        _file(
                            "klausur2025.pdf",
                            "/",
                            307200,
                            "https://moodle.hs-mannheim.de/webservice/pluginfile.php/779/mod_folder/content/0/klausur2025.pdf?forcedownload=1",
                            1791100000,
                            "application/pdf",
                        )
                    ],
                },
                {
                    "id": 9021,
                    "url": "https://moodle.hs-mannheim.de/mod/quiz/view.php?id=9021",
                    "name": "Probeklausur",
                    "visible": 0,
                    "uservisible": True,
                    "modname": "quiz",
                    "modplural": "Tests",
                },
                {
                    "id": 9022,
                    "url": "https://moodle.hs-mannheim.de/mod/choice/view.php?id=9022",
                    "name": "Evaluation",
                    "visible": 1,
                    "uservisible": False,
                    "modname": "choice",
                    "modplural": "Abstimmungen",
                    "availabilityinfo": "<div>Nicht verfügbar, es sei denn: <strong>Einschreibung</strong></div>",
                },
                {
                    "id": 9023,
                    "url": "https://moodle.hs-mannheim.de/mod/page/view.php?id=9023",
                    "name": "Lernziele",
                    "visible": 1,
                    "uservisible": True,
                    "modname": "page",
                    "modplural": "Textseiten",
                },
            ],
        },
    ]
}


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
            if fmt != "json":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            if function == SITE_INFO_FUNCTION:
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
            if function == COURSES_FUNCTION:
                if not rec.form_value("userid"):
                    return self._send_json(
                        200,
                        {
                            "exception": "invalid_parameter_exception",
                            "errorcode": "invalidparameter",
                            "message": "userid is missing",
                        },
                    )
                return self._send_json(200, COURSES)
            if function == CONTENTS_FUNCTION:
                try:
                    course_id = int(rec.form_value("courseid") or "")
                except ValueError:
                    return self._send_json(
                        200,
                        {
                            "exception": "invalid_parameter_exception",
                            "errorcode": "invalidparameter",
                            "message": "courseid is missing",
                        },
                    )
                return self._send_json(200, COURSE_CONTENTS.get(course_id, []))
            return self._send_json(
                200,
                {
                    "exception": "webservice_access_exception",
                    "errorcode": "accessexception",
                    "message": "Access to the specified function is not allowed",
                },
            )

    return Handler
