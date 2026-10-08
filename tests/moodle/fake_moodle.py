"""Lokaler Fake-Moodle-Server (nur stdlib, nur 127.0.0.1).

Bildet die beiden Web-Service-Endpunkte nach, die für den Login gebraucht
werden (siehe real-fixtures/NOTES.md):

    POST /login/token.php
        username, password, service=moodle_mobile_app
        -> 200 {"token": ..., "privatetoken": ...}
        -> 200 {"error": ..., "errorcode": "invalidlogin"}
    POST /webservice/rest/server.php
        wstoken, wsfunction=core_webservice_get_site_info, moodlewsrestformat=json
        -> 200 {"sitename", "username", "fullname", "userid", ...}
        -> 200 {"exception": ..., "errorcode": "invalidtoken"}

Über ``token_mode`` und ``site_info_mode`` lassen sich Fehlerfälle schalten.
"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_ENDPOINT = "/login/token.php"
REST_ENDPOINT = "/webservice/rest/server.php"


@dataclass
class RecordedRequest:
    method: str
    path: str
    form: dict[str, list[str]]
    headers: dict[str, str]

    def first(self, key: str, default=None):
        values = self.form.get(key)
        return values[0] if values else default


@dataclass
class FakeMoodle:
    username: str
    password: str
    token: str = ""
    sitename: str = "Lernplattform TH-MA"
    fullname: str = "Erika Beispiel"
    userid: int = 4242
    token_mode: str = "normal"  # normal | wrong_password | server_error | html
    site_info_mode: str = "normal"  # normal | invalid_token | server_error | html | garbage
    requests: list[RecordedRequest] = field(default_factory=list)
    issued_tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)
    port: int = 0
    _server: ThreadingHTTPServer | None = None

    def __post_init__(self) -> None:
        if not self.token:
            self.token = "moodle-token-" + secrets.token_hex(12)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeMoodle":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.path == path]


def _make_handler(world: FakeMoodle):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # still
            pass

        def _record(self, body: bytes) -> RecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            ctype = self.headers.get("Content-Type", "")
            form = (
                urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
                if "form-urlencoded" in ctype
                else {}
            )
            rec = RecordedRequest(
                method=self.command,
                path=parsed.path,
                form=form,
                headers={k: v for k, v in self.headers.items()},
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, payload: dict, status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _html(self, body: str, status: int = 200) -> None:
            self._send(status, body.encode("utf-8"), "text/html; charset=utf-8")

        def do_GET(self):
            self._record(b"")
            self._html("<html><body><h1>Fake Moodle</h1></body></html>", 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)
            if rec.path == TOKEN_ENDPOINT:
                return self._token(rec)
            if rec.path == REST_ENDPOINT:
                return self._site_info(rec)
            return self._html("<html><body><h1>404 Not Found</h1></body></html>", 404)

        # -- Endpunkte ---------------------------------------------------
        def _token(self, rec: RecordedRequest) -> None:
            if world.token_mode == "server_error":
                return self._html("<html><body><h1>503 Service Unavailable</h1></body></html>", 503)
            if world.token_mode == "html":
                return self._html("<html><body><h1>Wartungsarbeiten</h1></body></html>")
            username = rec.first("username")
            password = rec.first("password")
            if world.token_mode == "wrong_password" or username != world.username or password != world.password:
                return self._json({"error": "Invalid login, please try again.", "errorcode": "invalidlogin"})
            with world.lock:
                world.issued_tokens.add(world.token)
            return self._json({"token": world.token, "privatetoken": secrets.token_hex(16)})

        def _site_info(self, rec: RecordedRequest) -> None:
            if world.site_info_mode == "server_error":
                return self._html("<html><body><h1>503 Service Unavailable</h1></body></html>", 503)
            if world.site_info_mode == "html":
                return self._html("<html><body><h1>Kein JSON</h1></body></html>")
            if world.site_info_mode == "garbage":
                return self._send(200, b"not-json{", "application/json")
            token = rec.first("wstoken")
            if world.site_info_mode == "invalid_token" or token != world.token:
                return self._json(
                    {
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    }
                )
            if rec.first("wsfunction") != "core_webservice_get_site_info":
                return self._json({"errorcode": "invalidfunction", "message": "Unknown function"})
            return self._json(
                {
                    "sitename": world.sitename,
                    "username": world.username,
                    "fullname": world.fullname,
                    "userid": world.userid,
                    "siteurl": world.base_url,
                    "functions": [],
                }
            )

    return Handler
