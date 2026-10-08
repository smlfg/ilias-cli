"""Netzwerk-Sperre: erlaubt ausschließlich Loopback (127.0.0.1, ::1, localhost).

Wird im CLI-Subprozess über `PYTHONPATH` als `sitecustomize` geladen und im
pytest-Prozess von conftest.py installiert. Jeder Versuch, eine andere Adresse
zu erreichen, wird protokolliert und lässt den Test fehlschlagen - so kann kein
Test versehentlich moodle.hs-mannheim.de oder einen anderen echten Server
kontaktieren.
"""

from __future__ import annotations

import socket
from collections.abc import Callable

ALLOWED_NAMES = {"localhost", "127.0.0.1", "::1", "localhost.localdomain", "ip6-localhost"}


def is_loopback(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host in ALLOWED_NAMES or host.startswith("127.")


def install(record: Callable[[str], None]) -> None:
    """Patcht socket im aktuellen Prozess; verbotene Ziele werden an `record` gemeldet."""

    orig_getaddrinfo = socket.getaddrinfo
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex

    def _check_addr(sock: socket.socket, address: object) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address:
            if not is_loopback(address[0]):
                record(f"connect {address[0]}:{address[1]}")
                raise ConnectionRefusedError(f"moodle test sandbox: connection to {address[0]} blocked")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not is_loopback(host):
            record(f"getaddrinfo {host}")
            raise socket.gaierror(socket.EAI_NONAME, f"moodle test sandbox: DNS for {host!r} blocked")
        return orig_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(self, address):
        _check_addr(self, address)
        return orig_connect(self, address)

    def guarded_connect_ex(self, address):
        _check_addr(self, address)
        return orig_connect_ex(self, address)

    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.socket.connect = guarded_connect  # type: ignore[assignment]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[assignment]
