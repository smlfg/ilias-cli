"""Tests für den Session-Store (Keyring + Datei-Fallback)."""

from __future__ import annotations

import stat

from ilias_core.config import Config, load_config
from ilias_core.session import SessionStore


def test_keyring_roundtrip(config_dir, memory_keyring):
    cfg = load_config()
    store = SessionStore(cfg)

    store.save({"PHPSESSID": "abc", "ilClientId": "iliashhn"})
    assert memory_keyring.store, "Keyring wurde nicht verwendet"
    assert not cfg.session_file.exists()

    assert store.load() == {"PHPSESSID": "abc", "ilClientId": "iliashhn"}

    store.clear()
    assert store.load() is None


def test_file_fallback_permissions(config_dir):
    cfg = load_config()
    store = SessionStore(cfg, force_file=True)

    store.save({"PHPSESSID": "abc"})

    path = cfg.session_file
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.load() == {"PHPSESSID": "abc"}

    store.clear()
    assert not path.exists()
    assert store.load() is None


def test_configurable_config_dir_is_used(tmp_path):
    custom = tmp_path / "custom-ilias"
    cfg = Config(config_dir=custom)
    store = SessionStore(cfg, force_file=True)
    store.save({"PHPSESSID": "xyz"})
    assert (custom / "session.json").is_file()
