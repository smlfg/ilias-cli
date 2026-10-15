"""Kleiner lokaler HTTP-Server für Fetcher-Härtungstests (nur 127.0.0.1, nur synthetische Daten).

Routen werden pro Test gesetzt: ``server.routes[path] = (status, headers, body)``. Jeder
Request wird mit Methode und Pfad protokolliert.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGGED_IN_HTML = (
    '<html><body><a href="logout.php?cmd=doLogout">Abmelden</a>'
    '<div class="ilContainerBlock">Inhalt</div></body></html>'
)


@dataclass
class MiniServer:
    routes: dict[str, tuple[int, dict[str, str], bytes]] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)
    port: int = 0
    _srv: ThreadingHTTPServer | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> MiniServer:
        world = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):  # noqa: N802
                world.requests.append((self.command, self.path))
                status, headers, body = world.routes.get(
                    self.path, (404, {"Content-Type": "text/html"}, b"<h1>404</h1>")
                )
                self.send_response(status)
                headers = dict(headers)
                headers.setdefault("Content-Length", str(len(body)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_POST = do_GET  # noqa: N815

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._srv.daemon_threads = True
        self.port = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()


class Store:
    """Session-Speicher mit einer synthetischen Session; speichert nie etwas."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    def load(self):
        return {"PHPSESSID": "synthetic-session-0000"}

    def save(self, cookies):  # Cookie-Rotation
        self.saved.append(dict(cookies))
