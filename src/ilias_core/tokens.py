"""Token-Speicher: OS-Keyring (bevorzugt) oder Datei mit 0600."""

from __future__ import annotations

import os
import re
from pathlib import Path

import keyring

from .config import config_dir

_SERVICE = "ilias-cli"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "default"


def _username(key: str) -> str:
    return f"moodle:{key}"


def _file_path(key: str) -> Path:
    return config_dir() / f"moodle-token-{_slug(key)}.txt"


def load_token(key: str) -> str | None:
    try:
        token = keyring.get_password(_SERVICE, _username(key))
        if token:
            return token
    except Exception:
        pass
    path = _file_path(key)
    try:
        data = path.read_text(encoding="utf-8").strip()
        return data or None
    except OSError:
        return None


def save_token(key: str, token: str) -> None:
    try:
        keyring.set_password(_SERVICE, _username(key), token)
        return
    except Exception:
        pass
    path = _file_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def delete_token(key: str) -> None:
    try:
        keyring.delete_password(_SERVICE, _username(key))
    except Exception:
        pass
    try:
        _file_path(key).unlink()
    except FileNotFoundError:
        pass
