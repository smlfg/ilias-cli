from __future__ import annotations

import os
from pathlib import Path

import keyring
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://ilias.hs-heilbronn.de"
LOGIN = "https://login.hs-heilbronn.de"


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):  # type: ignore[override]
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("ILIAS_CLI_CONFIG", str(cfg_dir / "config.toml"))
    yield cfg_dir
    keyring.set_keyring(original)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
