"""Pytest-Fixtures: Temp-Konfigurationsordner und In-Memory-Keyring."""

from __future__ import annotations

import pytest


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
