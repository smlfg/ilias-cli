"""Pytest-Fixtures: Temp-Konfigurationsordner, In-Memory-Keyring, Netzwerk-Sperre."""

from __future__ import annotations

import socket

import pytest

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class MemoryKeyring:
    """Minimales In-Memory-Backend, ersetzt den OS-Schlüsselbund in Tests."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.store.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.store[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        key = (service_name, username)
        if key not in self.store:
            raise KeyError(username)
        del self.store[key]


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Nur Loopback erlaubt; HTTP wird hier ohnehin per respx gemockt."""

    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect

    def guarded_getaddrinfo(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name not in _LOOPBACK and not name.startswith("127."):
            raise AssertionError(f"Netzwerkzugriff auf {name!r} in Unit-Tests verboten")
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(self, address):
        if isinstance(address, tuple) and str(address[0]) not in _LOOPBACK and not str(address[0]).startswith("127."):
            raise AssertionError(f"Verbindung zu {address[0]!r} in Unit-Tests verboten")
        return original_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    directory = tmp_path / "ilias-cli"
    directory.mkdir()
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(directory))
    return directory


@pytest.fixture
def memory_keyring() -> MemoryKeyring:
    return MemoryKeyring()


@pytest.fixture(autouse=True)
def patch_keyring(monkeypatch, memory_keyring):
    monkeypatch.setattr(
        "ilias_core.session._default_keyring", lambda: memory_keyring
    )
    return memory_keyring
