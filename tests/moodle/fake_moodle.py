"""Lokaler Fake-Moodle-Server (nur stdlib, nur 127.0.0.1).

Bildet die Endpunkte nach, die Login (F1) sowie Kurse/Inhalte (F2/F3) benutzen
(siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):

  POST /login/token.php              username, password, service=moodle_mobile_app
        -> {"token": ..., "privatetoken": null}
        -> {"error": "Invalid login, please try again", "errorcode": "invalidlogin"}
  POST /webservice/rest/server.php   wstoken, wsfunction, moodlewsrestformat
        wsfunction=core_webservice_get_site_info
          -> {"sitename", "username", "fullname", "userid", ...}
          -> {"exception": "moodle_exception", "errorcode": "invalidtoken", ...}
        wsfunction=core_enrol_get_users_courses (userid)
          -> [{"id", "shortname", "fullname", "visible", "category",
               "startdate", "enddate", ...}]
        wsfunction=core_course_get_contents (courseid)
          -> [{"id", "name", "section", "visible", "uservisible", "modules": [...]}]

Schalter für Fehlerszenarien: token_mode, rest_mode (site_info),
courses_mode und contents_mode (F2/F3).
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

# Startdaten der Fixture-Kurse (Europe/Berlin, als Unix-Timestamps):
# 2026-04-01 10:00+02:00 -> SoSe 2026 · 2026-10-01 10:00+02:00 -> WiSe 2026/27
START_Sose_2026 = 1775030400
END_Sose_2026 = 1790805540  # 2026-09-30 23:59+02:00
START_WiSe_2026 = 1790841600
END_WiSe_2026 = 1806530340  # 2027-03-31 23:59+02:00
FILE_TS_1 = 1790900000
FILE_TS_2 = 1791194400


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
    # courses_mode: normal | server_error | html | empty
    courses_mode: str = "normal"
    # contents_mode: normal | server_error | html
    contents_mode: str = "normal"
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

    def rest_requests_for(self, wsfunction: str) -> list[RecordedRequest]:
        return [r for r in self.requests_to(REST_PATH) if r.form_value("wsfunction") == wsfunction]

    # -- Fixtures ---------------------------------------------------------
    def courses_payload(self) -> list[dict]:
        """Mindestens 3 Kurse: zwei Semester, einer mit startdate 0 (ohne category)."""
        return [
            {
                "id": 101,
                "shortname": "MATHE-WS26",
                "fullname": "Mathematik 1 (WS 2026/27)",
                "displayname": "Mathematik 1 (WS 2026/27)",
                "enrolledusercount": 120,
                "idnumber": "",
                "visible": 1,
                "summary": "<p>Grundlagen der Mathematik.</p>",
                "summaryformat": 1,
                "format": "topics",
                "category": 17,
                "progress": None,
                "completed": False,
                "startdate": START_WiSe_2026,
                "enddate": END_WiSe_2026,
                "lastaccess": 1791000000,
                "isfavourite": False,
                "hidden": False,
                "overviewfiles": [],
                "timemodified": 1790000000,
            },
            {
                "id": 102,
                "shortname": "MATHE-UE",
                "fullname": "Mathematik Übungsgruppe (WS 2026/27)",
                "displayname": "Mathematik Übungsgruppe (WS 2026/27)",
                "enrolledusercount": 30,
                "idnumber": "",
                "visible": 1,
                "summary": "",
                "summaryformat": 1,
                "format": "topics",
                "category": 17,
                "progress": None,
                "completed": False,
                "startdate": START_WiSe_2026,
                "enddate": END_WiSe_2026,
                "lastaccess": 1791000000,
                "isfavourite": False,
                "hidden": False,
                "overviewfiles": [],
                "timemodified": 1790000000,
            },
            {
                "id": 201,
                "shortname": "PR1-SS26",
                "fullname": "Programmieren 1 (SS 2026)",
                "displayname": "Programmieren 1 (SS 2026)",
                "enrolledusercount": 95,
                "idnumber": "",
                "visible": 1,
                "summary": "<p>Programmieren mit Python.</p>",
                "summaryformat": 1,
                "format": "topics",
                "category": 18,
                "progress": None,
                "completed": False,
                "startdate": START_Sose_2026,
                "enddate": END_Sose_2026,
                "lastaccess": 1780000000,
                "isfavourite": False,
                "hidden": False,
                "overviewfiles": [],
                "timemodified": 1780000000,
            },
            {
                "id": 301,
                "shortname": "PHYS-ALT",
                "fullname": "Physik Überblick",
                "displayname": "Physik Überblick",
                "enrolledusercount": 10,
                "idnumber": "",
                "visible": 0,
                "summary": "",
                "summaryformat": 1,
                "format": "topics",
                # absichtlich keine "category": -> null im CLI
                "progress": None,
                "completed": False,
                "startdate": 0,
                "enddate": 0,
                "lastaccess": 0,
                "isfavourite": False,
                "hidden": True,
                "overviewfiles": [],
                "timemodified": 1780000000,
            },
        ]

    def contents_payload(self, courseid: int) -> list[dict] | None:
        base = self.base_url
        if courseid == 101:
            return [
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
                            "id": 9101,
                            "url": f"{base}/mod/label/view.php?id=9101",
                            "name": "<p>Willkommen zur <b>Mathematik 1</b> &Uuml;bung und Organisatorisches f&uuml;r alle Erstsemester mit vielen Details</p>",
                            "instance": 11,
                            "contextid": 771,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "label",
                            "modplural": "Texte",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                        },
                        {
                            "id": 9102,
                            "url": f"{base}/mod/forum/view.php?id=9102",
                            "name": "Ankündigungen",
                            "instance": 12,
                            "contextid": 772,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "forum",
                            "modplural": "Foren",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                        },
                        {
                            "id": 9103,
                            "url": f"{base}/mod/url/view.php?id=9103",
                            "name": "Skript-Webseite",
                            "instance": 13,
                            "contextid": 773,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "url",
                            "modplural": "Links",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                            "contents": [
                                {
                                    "type": "url",
                                    "filename": "Skript-Webseite",
                                    "filepath": "/",
                                    "filesize": 0,
                                    "fileurl": "https://example.org/mathe-skript",
                                    "timecreated": FILE_TS_1,
                                    "timemodified": FILE_TS_1,
                                    "sortorder": 0,
                                    "mimetype": "text/html",
                                    "isexternalfile": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "id": 502,
                    "name": "Übungsblätter",
                    "visible": 1,
                    "summary": "",
                    "summaryformat": 1,
                    "section": 1,
                    "hiddenbynumsections": 0,
                    "uservisible": True,
                    "modules": [
                        {
                            "id": 9001,
                            "url": f"{base}/mod/folder/view.php?id=9001",
                            "name": "Übungsblätter",
                            "instance": 33,
                            "contextid": 777,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "folder",
                            "modplural": "Verzeichnisse",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                            "contents": [
                                {
                                    "type": "file",
                                    "filename": "blatt00.pdf",
                                    "filepath": "/",
                                    "filesize": 42100,
                                    "fileurl": f"{base}/webservice/pluginfile.php/777/mod_folder/content/0/blatt00.pdf?forcedownload=1",
                                    "timecreated": FILE_TS_1,
                                    "timemodified": FILE_TS_1,
                                    "sortorder": 0,
                                    "mimetype": "application/pdf",
                                    "isexternalfile": False,
                                    "userid": 55,
                                    "author": "Prof. X",
                                    "license": "allrightsreserved",
                                },
                                {
                                    "type": "file",
                                    "filename": "blatt01.pdf",
                                    "filepath": "/Blatt 1/",
                                    "filesize": 183456,
                                    "fileurl": f"{base}/webservice/pluginfile.php/777/mod_folder/content/0/Blatt%201/blatt01.pdf?forcedownload=1",
                                    "timecreated": FILE_TS_1,
                                    "timemodified": FILE_TS_1,
                                    "sortorder": 1,
                                    "mimetype": "application/pdf",
                                    "isexternalfile": False,
                                    "userid": 55,
                                    "author": "Prof. X",
                                    "license": "allrightsreserved",
                                },
                                {
                                    "type": "file",
                                    "filename": "loesung01.pdf",
                                    "filepath": "/Blatt 1/Lösungen/",
                                    "filesize": 96500,
                                    "fileurl": f"{base}/webservice/pluginfile.php/777/mod_folder/content/0/Blatt%201/L%C3%B6sungen/loesung01.pdf?forcedownload=1",
                                    "timecreated": FILE_TS_2,
                                    "timemodified": FILE_TS_2,
                                    "sortorder": 2,
                                    "mimetype": "application/pdf",
                                    "isexternalfile": False,
                                    "userid": 55,
                                    "author": "Prof. X",
                                    "license": "allrightsreserved",
                                },
                                {
                                    "type": "file",
                                    "filename": "klausur_ws25.pdf",
                                    "filepath": "/[Klausur] Altklausuren/",
                                    "filesize": 512000,
                                    "fileurl": f"{base}/webservice/pluginfile.php/777/mod_folder/content/0/%5BKlausur%5D%20Altklausuren/klausur_ws25.pdf?forcedownload=1",
                                    "timecreated": FILE_TS_2,
                                    "timemodified": FILE_TS_2,
                                    "sortorder": 3,
                                    "mimetype": "application/pdf",
                                    "isexternalfile": False,
                                    "userid": 55,
                                    "author": "Prof. X",
                                    "license": "allrightsreserved",
                                },
                            ],
                            "contentsinfo": {
                                "filescount": 4,
                                "filessize": 834056,
                                "lastmodified": FILE_TS_2,
                                "mimetypes": ["application/pdf"],
                                "repositorytype": "",
                            },
                        },
                        {
                            "id": 9002,
                            "url": f"{base}/mod/resource/view.php?id=9002",
                            "name": "Merkblatt Übung (mit Ümläuten äöü)",
                            "instance": 34,
                            "contextid": 778,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "resource",
                            "modplural": "Dateien",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                            "contents": [
                                {
                                    "type": "file",
                                    "filename": "merkblatt.pdf",
                                    "filepath": "/",
                                    "filesize": 183456,
                                    "fileurl": f"{base}/webservice/pluginfile.php/778/mod_resource/content/1/merkblatt.pdf?forcedownload=1",
                                    "timecreated": FILE_TS_1,
                                    "timemodified": FILE_TS_1,
                                    "sortorder": 0,
                                    "mimetype": "application/pdf",
                                    "isexternalfile": False,
                                    "userid": 55,
                                    "author": "Prof. X",
                                    "license": "allrightsreserved",
                                }
                            ],
                        },
                        {
                            "id": 9003,
                            "url": f"{base}/mod/assign/view.php?id=9003",
                            "name": "Abgabe Blatt 1",
                            "instance": 35,
                            "contextid": 779,
                            "visible": 1,
                            "uservisible": False,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "assign",
                            "modplural": "Aufgaben",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                            "availabilityinfo": "<div>Nicht verfügbar, es sei denn: <b>Es ist nach dem 1. Oktober 2026</b></div>",
                        },
                        {
                            "id": 9004,
                            "url": f"{base}/mod/quiz/view.php?id=9004",
                            "name": "Test: Grundlagen",
                            "instance": 36,
                            "contextid": 780,
                            "visible": 0,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "quiz",
                            "modplural": "Tests",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                        },
                    ],
                },
                {
                    "id": 503,
                    "name": "Vorlesung",
                    "visible": 1,
                    "summary": "",
                    "summaryformat": 1,
                    "section": 2,
                    "hiddenbynumsections": 0,
                    "uservisible": True,
                    "modules": [
                        {
                            "id": 9005,
                            "url": f"{base}/mod/page/view.php?id=9005",
                            "name": "Lernziele & Überblick",
                            "instance": 37,
                            "contextid": 781,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "page",
                            "modplural": "Seiten",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                        },
                        {
                            "id": 9006,
                            "url": f"{base}/mod/choice/view.php?id=9006",
                            "name": "Umfrage [Termine]",
                            "instance": 38,
                            "contextid": 782,
                            "visible": 1,
                            "uservisible": False,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "choice",
                            "modplural": "Abstimmungen",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                            "availabilityinfo": "<p>Nur für <em>Gruppe A</em> sichtbar.</p>",
                        },
                    ],
                },
                {
                    "id": 504,
                    "name": "",
                    "visible": 1,
                    "summary": "",
                    "summaryformat": 1,
                    "section": 3,
                    "hiddenbynumsections": 0,
                    "uservisible": True,
                    "modules": [],
                },
            ]
        if courseid in (102, 201, 301):
            short = {102: "MATHE-UE", 201: "PR1-SS26", 301: "PHYS-ALT"}[courseid]
            return [
                {
                    "id": 600 + courseid,
                    "name": "Allgemeines",
                    "visible": 1,
                    "summary": "",
                    "summaryformat": 1,
                    "section": 0,
                    "hiddenbynumsections": 0,
                    "uservisible": True,
                    "modules": [
                        {
                            "id": 9500 + courseid,
                            "url": f"{base}/mod/forum/view.php?id={9500 + courseid}",
                            "name": f"Forum {short}",
                            "instance": 50,
                            "contextid": 900,
                            "visible": 1,
                            "uservisible": True,
                            "visibleoncoursepage": 1,
                            "modicon": "",
                            "modname": "forum",
                            "modplural": "Foren",
                            "indent": 0,
                            "noviewlink": False,
                            "completion": 0,
                        }
                    ],
                }
            ]
        return None


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

        def _send_json(self, status: int, payload) -> None:
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
            token = rec.form_value("wstoken") or ""
            function = rec.form_value("wsfunction") or ""
            fmt = rec.form_value("moodlewsrestformat") or ""
            if function == "core_webservice_get_site_info":
                return self._site_info(rec, token, function, fmt)
            if function == "core_enrol_get_users_courses":
                return self._users_courses(rec, token, fmt)
            if function == "core_course_get_contents":
                return self._course_contents(rec, token, fmt)
            return self._send_json(
                200,
                {
                    "exception": "webservice_access_exception",
                    "errorcode": "accessexception",
                    "message": "Access to the specified function is not allowed",
                },
            )

        def _check_token(self, token: str) -> str | None:
            with world.lock:
                return world.tokens.get(token)

        def _site_info(self, rec: RecordedRequest, token: str, function: str, fmt: str) -> None:
            if world.rest_mode == "server_error":
                return self._send_html(502, "<h1>502 Bad Gateway</h1>", "text/html; charset=UTF-8")
            if world.rest_mode == "html":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            if function != "core_webservice_get_site_info" or fmt != "json":
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
            username = self._check_token(token)
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

        def _users_courses(self, rec: RecordedRequest, token: str, fmt: str) -> None:
            if world.courses_mode == "server_error":
                return self._send_html(502, "<h1>502 Bad Gateway</h1>", "text/html; charset=UTF-8")
            if world.courses_mode == "html":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            if fmt != "json":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            username = self._check_token(token)
            if username is None:
                return self._send_json(
                    401,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    },
                )
            if world.courses_mode == "empty":
                return self._send_json(200, [])
            if not rec.form_value("userid"):
                return self._send_json(
                    200,
                    {
                        "exception": "invalid_parameter_exception",
                        "errorcode": "invalidparameter",
                        "message": "Missing required parameter: userid",
                    },
                )
            return self._send_json(200, world.courses_payload())

        def _course_contents(self, rec: RecordedRequest, token: str, fmt: str) -> None:
            if world.contents_mode == "server_error":
                return self._send_html(502, "<h1>502 Bad Gateway</h1>", "text/html; charset=UTF-8")
            if world.contents_mode == "html":
                return self._send_html(200, LOGIN_PAGE_HTML, "text/html; charset=UTF-8")
            if fmt != "json":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "accessexception",
                        "message": "Access to the specified function is not allowed",
                    },
                )
            username = self._check_token(token)
            if username is None:
                return self._send_json(
                    401,
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    },
                )
            raw = rec.form_value("courseid")
            try:
                courseid = int(raw or "")
            except ValueError:
                courseid = -1
            payload = world.contents_payload(courseid)
            if payload is None:
                return self._send_json(
                    200,
                    {
                        "exception": "invalid_parameter_exception",
                        "errorcode": "invalidparameter",
                        "message": f"Invalid course id: {raw}",
                    },
                )
            return self._send_json(200, payload)

    return Handler
