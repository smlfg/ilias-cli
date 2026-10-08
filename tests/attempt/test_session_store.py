from __future__ import annotations

import os
import stat
from pathlib import Path

import keyring
import pytest

from ilias_core import session
from ilias_core.models import SessionData


def _data() -> SessionData:
    return SessionData(base_url="https://ilias.hs-heilbronn.de", cookies={"PHPSESSID": "x", "ilClientId": "iliashhn"})


def test_save_load_delete_keyring() -> None:
    storage = session.save_session(_data())
    assert storage == "keyring"
    loaded = session.load_session()
    assert loaded is not None and loaded.cookies["PHPSESSID"] == "x"
    session.delete_session()
    assert session.load_session() is None


def test_file_fallback_permissions(monkeypatch: pytest.MonkeyPatch, isolated_env: Path) -> None:
    def boom(*args, **kwargs):
        raise keyring.errors.KeyringError("no keyring")

    monkeypatch.setattr(keyring, "set_password", boom)
    monkeypatch.setattr(keyring, "get_password", boom)
    storage = session.save_session(_data())
    assert storage == "file"
    path = isolated_env / "session.json"
    assert path.exists()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    loaded = session.load_session()
    assert loaded is not None and loaded.cookies["ilClientId"] == "iliashhn"
    session.delete_session()
    assert not path.exists()
