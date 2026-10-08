"""Lokaler Fake-Moodle-Server für Tests (nur stdlib, nur localhost).

Simuliert:
  POST /login/token.php -> {"token": "...", "privatetoken": "..."} oder Error
  POST /webservice/rest/server.php (core_webservice_get_site_info) -> Site-Info oder invalidtoken
"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    form: dict[str, list[str]]
    cookies: dict[str, str]


@dataclass
class FakeMoodleWorld:
    username: str
    password: str
    sitename: str = "Lernplattform TH-MA"
    fullname: str = "Test User"
    userid: int = 42
    siteurl: str = "https://moodle.hs-mannheim.de"

    # Fehlerszenarien
    token_mode: str = "normal"  # normal | invalidlogin | error500 | garbage
    siteinfo_mode: str = "normal"  # normal | invalidtoken | error503 | garbage

    requests: list[RecordedRequest] = field(default_factory=list)
    issued_tokens: set[str] = field(default_factory=set)
    valid_tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    port: int = 0
    _server: ThreadingHTTPServer | None = field(default=None, repr=False)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeMoodleWorld":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self.port = self._server.server_address[1]
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass

    def expire_all_tokens(self) -> None:
        with self.lock:
            self.valid_tokens.clear()

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.path == path]


def _make_handler(world: FakeMoodleWorld):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _record(self, body: bytes) -> RecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            cookies: dict[str, str] = {}
            for raw in self.headers.get_all("Cookie") or []:
                from http.cookies import SimpleCookie

                c = SimpleCookie()
                try:
                    c.load(raw)
                except Exception:
                    continue
                cookies.update({k: v.value for k, v in c.items()})
            ctype = self.headers.get("Content-Type", "")
            form = (
                urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
                if "form-urlencoded" in ctype
                else {}
            )
            rec = RecordedRequest(
                method=self.command,
                path=parsed.path,
                query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                headers={k: v for k, v in self.headers.items()},
                form=form,
                cookies=cookies,
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send_json(self, status: int, data: dict[str, Any]):
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, must-revalidate, max-age=0")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_html(self, status: int, html: str):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            self._record(body)

            if self.path.startswith("/login/token.php"):
                self._handle_token(body)
            elif self.path.startswith("/webservice/rest/server.php"):
                self._handle_siteinfo(body)
            else:
                self._send_json(404, {"error": "Not found"})

        def _handle_token(self, body: bytes):
            form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]
            service = form.get("service", [""])[0]

            if world.token_mode == "error500":
                self._send_json(500, {"error": "Internal Server Error"})
                return

            if world.token_mode == "garbage":
                self._send_html(200, "<html><body>Wartung</body></html>")
                return

            if username == world.username and password == world.password and service == "moodle_mobile_app":
                token = "moodle_token_" + secrets.token_hex(16)
                privatetoken = "private_" + secrets.token_hex(16)
                with world.lock:
                    world.issued_tokens.add(token)
                    world.valid_tokens.add(token)
                self._send_json(200, {"token": token, "privatetoken": privatetoken})
            else:
                self._send_json(200, {"error": "Invalid login", "errorcode": "invalidlogin"})

        def _handle_siteinfo(self, body: bytes):
            # Params sind in der Query String für GET, aber Moodle Mobile nutzt POST mit params
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            wstoken = query.get("wstoken", [""])[0]
            wsfunction = query.get("wsfunction", [""])[0]

            if world.siteinfo_mode == "error503":
                self._send_json(503, {"error": "Service Unavailable"})
                return

            if world.siteinfo_mode == "garbage":
                self._send_html(200, "<html><body>Wartung</body></html>")
                return

            if wsfunction != "core_webservice_get_site_info":
                self._send_json(400, {"error": "Unknown function", "errorcode": "unknownfunction"})
                return

            with world.lock:
                valid = wstoken in world.valid_tokens

            if not valid:
                self._send_json(200, {"exception": "invalid_token", "errorcode": "invalidtoken", "message": "Invalid token"})
                return

            self._send_json(
                200,
                {
                    "sitename": world.sitename,
                    "username": world.username,
                    "fullname": world.fullname,
                    "userid": world.userid,
                    "siteurl": world.base_url,
                    "functions": [],
                    "downloadfiles": 1,
                    "userpictureurl": "",
                    "lang": "de",
                    "calendartype": "gregorian",
                },
            )

    return Handler