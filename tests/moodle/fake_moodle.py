"""Lokaler Fake-Moodle-Server (nur stdlib, nur 127.0.0.1).

Bildet die offiziellen Mobile-Webservice-Endpunkte nach (siehe real-fixtures/NOTES.md):
  POST {base}/login/token.php
    data: username, password, service=moodle_mobile_app
    ok:   {"token": "...", "privatetoken": "..."}
    fail: {"error": "...", "errorcode": "invalidlogin"}
  POST {base}/webservice/rest/server.php
    data: wstoken, wsfunction=core_webservice_get_site_info, moodlewsrestformat=json
    ok:   {"sitename","username","fullname","userid",...}
    fail: {"exception":"webservice_access_exception","errorcode":"invalidtoken","message":"..."}
"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    form: dict[str, list[str]]


@dataclass
class FakeMoodle:
    username: str = "test.user"
    password: str = "T3st-P4ssw0rt-9Zx!"
    token: str = "testtoken1234567890abcdef"
    sitename: str = "Lernplattform TH-MA"
    fullname: str = "Test User"
    userid: int = 42
    # Fehlerschalter
    token_mode: str = "normal"  # normal | error500 | html
    siteinfo_mode: str = "normal"  # normal | invalidtoken | error500 | html
    requests: list[RecordedRequest] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    port: int = 0
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeMoodle":
        server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self.port = server.server_address[1]
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def requests_to(self, path_suffix: str) -> list[RecordedRequest]:
        with self.lock:
            return [r for r in self.requests if r.path.endswith(path_suffix)]


def _make_handler(world: FakeMoodle):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # still
            pass

        def _record(self, body: bytes) -> RecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            ctype = self.headers.get("Content-Type", "")
            if "form-urlencoded" in ctype:
                form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            else:
                form = {}
            rec = RecordedRequest(
                method=self.command,
                path=parsed.path,
                query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                headers={k: v for k, v in self.headers.items()},
                form=form,
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send_json(self, status: int, obj: dict) -> None:
            data = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _send_html(self, status: int, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)
            if rec.path.endswith("/login/token.php"):
                self._handle_token(rec)
            elif rec.path.endswith("/webservice/rest/server.php"):
                self._handle_siteinfo(rec)
            else:
                self._send_html(404, "<h1>404 Not Found</h1>")

        def do_GET(self) -> None:
            rec = self._record(b"")
            if rec.path.endswith("/login/token.php") or rec.path.endswith("/webservice/rest/server.php"):
                # Nur POST erlaubt; GET -> unerwartet (für Robustheit trotzdem JSON-Fehler).
                self._send_json(405, {"error": "Method not allowed", "errorcode": "invalidmethod"})
            else:
                self._send_html(404, "<h1>404 Not Found</h1>")

        def _handle_token(self, rec: RecordedRequest) -> None:
            if world.token_mode == "error500":
                return self._send_html(500, "<h1>500 Internal Server Error</h1>")
            if world.token_mode == "html":
                return self._send_html(
                    200,
                    "<!DOCTYPE html><html><head><title>Anmelden</title></head>"
                    "<body><h1>Wartungsarbeiten</h1></body></html>",
                )
            form = {k: (v[0] if v else "") for k, v in rec.form.items()}
            if (
                form.get("username") == world.username
                and form.get("password") == world.password
                and form.get("service") == "moodle_mobile_app"
            ):
                return self._send_json(
                    200, {"token": world.token, "privatetoken": "private-" + secrets.token_hex(8)}
                )
            return self._send_json(
                200, {"error": "Invalid login, please try again", "errorcode": "invalidlogin"}
            )

        def _handle_siteinfo(self, rec: RecordedRequest) -> None:
            if world.siteinfo_mode == "error500":
                return self._send_html(503, "<h1>503 Service Unavailable</h1>")
            if world.siteinfo_mode == "html":
                return self._send_html(
                    200,
                    "<!DOCTYPE html><html><head><title>Moodle</title></head>"
                    "<body><h1>Unerwartet</h1></body></html>",
                )
            if world.siteinfo_mode == "invalidtoken":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    },
                )
            form = {k: (v[0] if v else "") for k, v in rec.form.items()}
            if form.get("wstoken") != world.token:
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid token - token not found",
                    },
                )
            if form.get("wsfunction") != "core_webservice_get_site_info":
                return self._send_json(
                    200,
                    {
                        "exception": "webservice_access_exception",
                        "errorcode": "invalidfunction",
                        "message": "Invalid function",
                    },
                )
            return self._send_json(
                200,
                {
                    "sitename": world.sitename,
                    "username": world.username,
                    "fullname": world.fullname,
                    "userid": world.userid,
                    "userpictureurl": f"{world.base_url}/user/pic.png",
                },
            )

    return Handler
