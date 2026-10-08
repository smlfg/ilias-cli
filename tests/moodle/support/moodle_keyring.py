"""Test-Keyring-Backend: schreibt Einträge als JSON nach $MOODLE_KEYRING_FILE.

Damit können die Tests prüfen, was im "Schlüsselbund" landet: Token ja,
Passwort/TOTP/Token-Fremdding niemals. Wird im CLI-Subprozess über
PYTHON_KEYRING_BACKEND=moodle_keyring.FileKeyring geladen.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class FileKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    @property
    def _path(self) -> Path:
        return Path(os.environ["MOODLE_KEYRING_FILE"])

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def get_password(self, service: str, username: str) -> str | None:
        return self._load().get(f"{service}\x00{username}")

    def set_password(self, service: str, username: str, password: str) -> None:
        data = self._load()
        data[f"{service}\x00{username}"] = password
        self._save(data)

    def delete_password(self, service: str, username: str) -> None:
        data = self._load()
        key = f"{service}\x00{username}"
        if key not in data:
            raise PasswordDeleteError("not found")
        del data[key]
        self._save(data)
