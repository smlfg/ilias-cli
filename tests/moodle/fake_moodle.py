"""Fake-Moodle-Server (stdlib http.server, nur 127.0.0.1)."""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SITENAME = "Lernplattform TH-MA"
FULLNAME = "Max Mustermann"
USERNAME = "mmustermann"
PASSWORD = "Moodle-Pa55w0rd-9!"


@dataclass
class RecordedRequest:
    method: str
    path: str
    form: dict[str, list[str]]


class FakeMoodle:
    token_mode = "ok"  # ok | error500 | html
    rest_mode = "ok"  # ok | invalidtoken | error500 | html

    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self.valid_tokens: set[str] = set()
        self.last_token: str | None = None
        self._server: ThreadingHTTPServer | None = None
        self.port = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeMoodle":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def invalidate_tokens(self) -> None:
        self.valid_tokens.clear()

    def _handler(self):
        world = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, status: int, body: bytes, ctype: str = "application/json"):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
                world.requests.append(RecordedRequest(self.command, urllib.parse.urlsplit(self.path).path, form))
                path = urllib.parse.urlsplit(self.path).path
                if path == "/login/token.php":
                    return self._token(form)
                if path == "/webservice/rest/server.php":
                    return self._rest(form)
                return self._send(404, b'{"exception": "not found"}')

            def do_GET(self):
                return self._send(405, b"<html><body>Method not allowed</body></html>", "text/html")

            def _token(self, form):
                if world.token_mode == "error500":
                    return self._send(500, b"<html><body>500 Internal Server Error</body></html>", "text/html")
                if world.token_mode == "html":
                    return self._send(200, b"<html><head><title>Moodle</title></head><body>Maintenance</body></html>", "text/html")
                if form.get("service") == ["moodle_mobile_app"] and form.get("username") == [USERNAME] and form.get("password") == [PASSWORD]:
                    token = "MOODLETOKEN-" + secrets.token_hex(16)
                    world.valid_tokens.add(token)
                    world.last_token = token
                    return self._send(200, json.dumps({"token": token, "privatetoken": "priv-" + secrets.token_hex(8)}).encode())
                return self._send(200, json.dumps({"error": "Ungültiger Benutzername oder Passwort.", "errorcode": "invalidlogin"}).encode())

            def _rest(self, form):
                if world.rest_mode == "error500":
                    return self._send(503, b"<html><body>503 Service Unavailable</body></html>", "text/html")
                if world.rest_mode == "html":
                    return self._send(200, b"<html><body>Moodle login page</body></html>", "text/html")
                token = (form.get("wstoken") or [""])[0]
                if world.rest_mode == "invalidtoken" or token not in world.valid_tokens:
                    return self._send(200, json.dumps({
                        "exception": "moodle_exception",
                        "errorcode": "invalidtoken",
                        "message": "Invalid web service token",
                    }).encode())
                if form.get("wsfunction") != ["core_webservice_get_site_info"]:
                    return self._send(200, json.dumps({"exception": "moodle_exception", "errorcode": "unknownwsfunction"}).encode())
                return self._send(200, json.dumps({
                    "sitename": SITENAME,
                    "username": USERNAME,
                    "fullname": FULLNAME,
                    "userid": 42,
                }).encode())

        return Handler
