"""Lokaler Fake-Moodle-HTTP-Server für Tests (stdlib, nur localhost).

Hört auf 127.0.0.1 auf einen zugewiesenen Port.
Behandelte Endpunkte:
  POST /login/token.php   -> success JSON {"token": "..."} oder error JSON {"error": "...", "errorcode": "invalidlogin"}
  POST /webservice/rest/server.php -> site-info JSON oder error JSON
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass, field
from typing import dict as dict_t


KC_BASE = "http://127.0.0.1"


@dataclass
class MoodleRecordedRequest:
    method: str
    path: str
    query: dict_t[str, list[str]]
    form: dict_t[str, list[str]]
    headers: dict_t[str, str]


@dataclass
class MoodleFakeWorld:
    username: str = "moodleuser"
    password: str = "moodlepass123"
    requests: list[MoodleRecordedRequest] = field(default_factory=list)

    port: int = 0
    _server: ThreadingHTTPServer | None = field(default_factory=None)
    _thread: threading.Thread | None = field(default_factory=None)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "MoodleFakeWorld":
        handler = _make_handler(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_address[1]
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


def _make_handler(world: MoodleFakeWorld):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # still
            pass

        def _record(self, body: bytes) -> MoodleRecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            cookies: dict[str, str] = {}
            for raw in self.headers.get_all("Cookie") or []:
                from http.cookies import SimpleCookie
                c = SimpleCookie()
                try:
                    c.load(raw)
                except Exception:
                    continue
                for morsel in c.values():
                    cookies[morsel.key] = morsel.value
            ctype = self.headers.get("Content-Type", "")
            form = {}
            if "form-urlencoded" in ctype:
                try:
                    form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
                except Exception:
                    form = {}
            rec = MoodleRecordedRequest(
                method=self.command,
                path=parsed.path,
                query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                form=form,
                headers=dict(self.headers),
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send_json(self, status: int, data: dict) -> None:
            data_bytes = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data_bytes)))
            self.send_header("Cache-Control", "no-store, must-revalidate, max-age=0")
            self.end_headers()
            self.wfile.write(data_bytes)

        def do_GET(self):  # not used for Moodle flow but required
            self._send_json(404, {"error": "GET not allowed"})

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)

            path = rec.path
            q = {k: v[0] for k, v in rec.query.items()}

            # ---- /login/token.php ----
            if path == "/login/token.php":
                form = {k: v[0] for k, v in rec.form.items()}
                username = form.get("username", "")
                password = form.get("password", "")
                service = form.get("service", "")

                # Check credentials
                if username == world.username and password == world.password:
                    # Success: return token
                    token = "moodletoken-" + username + "-privatetoken-" + username
                    self._send_json(200, {"token": token, "privatetoken": token + "-priv"})
                else:
                    # Error: invalid login
                    self._send_json(200, {"error": "The username and/or password are incorrect.", "errorcode": "invalidlogin"})

            # ---- /webservice/rest/server.php ----
            elif path == "/webservice/rest/server.php":
                form = {k: v[0] for k, v in rec.form.items()}
                wstoken = form.get("wstoken", "")
                wsfunction = form.get("wsfunction", "")
                fmt = form.get("moodlewsrestformat", "")

                # Validate
                if wstoken == "validtoken123" and wsfunction == "core_webservice_get_site_info" and fmt == "json":
                    self._send_json(200, {
                        "sitename": "Lernplattform TH-MA",
                        "username": world.username,
                        "fullname": "Test User",
                        "userid": 12345,
                    })
                else:
                    # Invalid token
                    self._send_json(200, {
                        "exception": "invalidwstoken",
                        "errorcode": "invalidtoken",
                    })

            else:
                self._send_json(404, {"error": "Not found"})

        # Ensure headers are serialized properly
        def send_header(self, *args, **kwargs):
            # Override to avoid log_message issues
            BaseHTTPRequestHandler.send_header(self, *args, **kwargs)

    return Handler


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _is_loopback_host(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host in {"localhost", "127.0.0.1", "::1", "localhost.localdomain"} or host.startswith("127.")


# ---------------------------------------------------------------------------
# Pytest Support
# ---------------------------------------------------------------------------

from pathlib import Path
import stat


def file_mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_secret_in_text(secret: str, text: str | bytes) -> bool:
    import urllib.parse, base64
    data = text.encode("utf-8", "replace") if isinstance(text, str) else text
    raw = secret.encode("utf-8")
    variants = [raw, urllib.parse.quote(secret).encode(), urllib.parse.quote_plus(secret).encode(), base64.b64encode(raw)]
    return any(v in data for v in variants)


def find_secret_in_paths(secret: str, paths: list[Path]) -> list[Path]:
    hits: list[Path] = []
    for root in paths:
        root = Path(root)
        if not root.exists():
            continue
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]
        for f in files:
            try:
                if find_secret_in_text(secret, f.read_bytes()):
                    hits.append(f)
            except OSError:
                continue
    return hits