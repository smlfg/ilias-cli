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


def _epoch(year: int, month: int, day: int) -> int:
    from datetime import datetime, timezone

    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def default_courses() -> list[dict]:
    return [
        {
            "id": 1234,
            "shortname": "MA1-WS26",
            "fullname": "Mathe 1 (WS 2026/27)",
            "displayname": "Mathe 1 (WS 2026/27)",
            "category": 17,
            "visible": 1,
            "startdate": _epoch(2026, 10, 1),
            "enddate": _epoch(2027, 3, 31),
            "format": "topics",
            "summary": "<p>Lineare Algebra und Analysis</p>",
        },
        {
            "id": 1235,
            "shortname": "MA2-SS27",
            "fullname": "Mathe 2 (SoSe 2027)",
            "displayname": "Mathe 2 (SoSe 2027)",
            "category": 17,
            "visible": 1,
            "startdate": _epoch(2027, 4, 1),
            "enddate": _epoch(2027, 9, 30),
            "format": "topics",
            "summary": "",
        },
        {
            "id": 1236,
            "shortname": "PR1",
            "fullname": "Programmieren 1",
            "displayname": "Programmieren 1",
            "category": 17,
            "visible": 1,
            "startdate": _epoch(2027, 2, 1),
            "enddate": _epoch(2027, 3, 31),
            "format": "topics",
            "summary": "",
        },
        {
            "id": 1237,
            "shortname": "BIO",
            "fullname": "Biologie Einführung",
            "displayname": "Biologie Einführung",
            "category": 9,
            "visible": 1,
            "startdate": 0,
            "enddate": 0,
            "format": "topics",
            "summary": "",
        },
        {
            "id": 1238,
            "shortname": "ALT",
            "fullname": "[Klausur] Altklausuren",
            "displayname": "[Klausur] Altklausuren",
            "category": 9,
            "visible": 0,
            "startdate": _epoch(2026, 4, 1),
            "enddate": 0,
            "format": "topics",
            "summary": "",
        },
    ]


def _file(name, path, size=183456, mtime=_epoch(2026, 10, 15), mime="application/pdf"):
    import urllib.parse

    return {
        "type": "file",
        "filename": name,
        "filepath": path,
        "filesize": size,
        "fileurl": f"{{base}}/webservice/pluginfile.php/777/mod_folder/content/0/"
        + urllib.parse.quote(path.strip("/") + "/" + name)
        + "?forcedownload=1",
        "timecreated": mtime,
        "timemodified": mtime,
        "mimetype": mime,
        "isexternalfile": False,
        "sortorder": 0,
    }


def default_contents() -> dict[int, list[dict]]:
    return {
        1234: [
            {
                "id": 501,
                "name": "Allgemeines",
                "visible": 1,
                "summary": "",
                "summaryformat": 1,
                "section": 0,
                "uservisible": True,
                "modules": [
                    {
                        "id": 9001,
                        "url": "{base}/mod/url/view.php?id=9001",
                        "name": "Kursseite",
                        "modname": "url",
                        "visible": 1,
                        "uservisible": True,
                        "contents": [
                            {
                                "type": "url",
                                "filename": "FH-Portal",
                                "fileurl": "https://www.example.edu/fh",
                                "timemodified": _epoch(2026, 10, 1),
                            }
                        ],
                    },
                    {
                        "id": 9002,
                        "url": "{base}/mod/forum/view.php?id=9002",
                        "name": "Ankündigungen",
                        "modname": "forum",
                        "visible": 1,
                        "uservisible": True,
                    },
                    {
                        "id": 9003,
                        "url": "{base}/mod/label/view.php?id=9003",
                        "name": "<p>Herzlich willkommen <b>im Kurs</b>!</p>",
                        "modname": "label",
                        "visible": 1,
                        "uservisible": True,
                    },
                ],
            },
            {
                "id": 502,
                "name": "Übungen",
                "visible": 1,
                "summary": "",
                "section": 1,
                "uservisible": True,
                "modules": [
                    {
                        "id": 9010,
                        "url": "{base}/mod/folder/view.php?id=9010",
                        "name": "Übungsblätter",
                        "modname": "folder",
                        "visible": 1,
                        "uservisible": True,
                        "contents": [
                            _file("blatt01.pdf", "/Blatt 1/"),
                            _file("blatt01_lsg.pdf", "/Blatt 1/Lösungen/", size=95432),
                            _file("blatt02.pdf", "/Blatt 2/", size=260000),
                        ],
                    },
                    {
                        "id": 9011,
                        "url": "{base}/mod/assign/view.php?id=9011",
                        "name": "Hausaufgabe 1",
                        "modname": "assign",
                        "visible": 1,
                        "uservisible": True,
                    },
                    {
                        "id": 9012,
                        "url": "{base}/mod/quiz/view.php?id=9012",
                        "name": "Probeklausur",
                        "modname": "quiz",
                        "visible": 0,
                        "uservisible": True,
                    },
                ],
            },
            {
                "id": 503,
                "name": "Material",
                "visible": 1,
                "summary": "",
                "section": 2,
                "uservisible": True,
                "modules": [
                    {
                        "id": 9020,
                        "url": "{base}/mod/resource/view.php?id=9020",
                        "name": "Skript.pdf",
                        "modname": "resource",
                        "visible": 1,
                        "uservisible": True,
                        "contents": [
                            _file("Skript.pdf", "/", size=4194304, mime="application/pdf")
                        ],
                    },
                    {
                        "id": 9021,
                        "url": "{base}/mod/page/view.php?id=9021",
                        "name": "Kursübersicht",
                        "modname": "page",
                        "visible": 1,
                        "uservisible": True,
                    },
                    {
                        "id": 9022,
                        "url": "{base}/mod/choice/view.php?id=9022",
                        "name": "Terminumfrage",
                        "modname": "choice",
                        "visible": 1,
                        "uservisible": True,
                    },
                    {
                        "id": 9023,
                        "url": "{base}/mod/folder/view.php?id=9023",
                        "name": "[Klausur] Altklausuren",
                        "modname": "folder",
                        "visible": 1,
                        "uservisible": True,
                        "contents": [_file("klausur2025.pdf", "/2025/", size=524288)],
                    },
                ],
            },
            {
                "id": 504,
                "name": "Prüfungsorganisation",
                "visible": 1,
                "summary": "",
                "section": 3,
                "uservisible": True,
                "modules": [
                    {
                        "id": 9030,
                        "url": "{base}/mod/assign/view.php?id=9030",
                        "name": "Abschlussprojekt",
                        "modname": "assign",
                        "visible": 1,
                        "uservisible": False,
                        "availabilityinfo": "<div>Nicht verfügbar, es sei denn: die vorherige Aktivität ist abgeschlossen</div>",
                    }
                ],
            },
            {
                "id": 505,
                "name": "",
                "visible": 1,
                "summary": "",
                "section": 4,
                "uservisible": True,
                "modules": [],
            },
        ],
        1235: [
            {
                "id": 551,
                "name": "Allgemeines",
                "visible": 1,
                "summary": "",
                "section": 0,
                "uservisible": True,
                "modules": [],
            }
        ],
        1236: [
            {
                "id": 561,
                "name": "Allgemeines",
                "visible": 1,
                "summary": "",
                "section": 0,
                "uservisible": True,
                "modules": [],
            }
        ],
        1237: [],
        1238: [
            {
                "id": 601,
                "name": "Allgemeines",
                "visible": 1,
                "summary": "",
                "section": 0,
                "uservisible": True,
                "modules": [
                    {
                        "id": 6100,
                        "url": "{base}/mod/folder/view.php?id=6100",
                        "name": "[Klausur] Altklausuren",
                        "modname": "folder",
                        "visible": 1,
                        "uservisible": True,
                        "contents": [_file("klausur2024.pdf", "/", size=200000)],
                    }
                ],
            }
        ],
    }


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
    courses: list[dict] = field(default_factory=lambda: default_courses())
    contents: dict[int, list[dict]] = field(default_factory=lambda: default_contents())

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

        def _relay(self, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).replace("{base}", world.base_url)
            self._send(200, body)

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
            if fmt != "json":
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
            if function == "core_webservice_get_site_info":
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
            if function == "core_enrol_get_users_courses":
                if rec.form_value("userid") != str(world.userid):
                    return self._send_json(
                        200,
                        {
                            "exception": "moodle_exception",
                            "errorcode": "invalidparameter",
                            "message": "Invalid parameter value detected",
                        },
                    )
                return self._relay(world.courses)
            if function == "core_course_get_contents":
                try:
                    courseid = int(rec.form_value("courseid") or "")
                except ValueError:
                    courseid = -1
                if courseid in world.contents:
                    return self._relay(world.contents[courseid])
                return self._send_json(
                    200,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidparameter",
                        "message": "Invalid parameter value detected",
                    },
                )
            return self._send_json(
                200,
                {
                    "exception": "webservice_access_exception",
                    "errorcode": "accessexception",
                    "message": f"The requested web service function '{function}' is not available",
                },
            )

    return Handler
