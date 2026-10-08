"""Session-Stores: keyring (OS-Schlüsselbund) mit Datei-Fallback (0600).

Cookies werden niemals geloggt oder ausgeben - sie landen nur im Store.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from ilias_core.config import Config
from ilias_core.errors import KeyringUnavailableError
from ilias_core.models import SessionData

KEYRING_SERVICE = "ilias-cli"
KEYRING_KEY = "session"


def _serialize(data: SessionData) -> str:
    return json.dumps(
        {
            "base_url": data.base_url,
            "client_id": data.client_id,
            "cookies": data.cookies,
            "username": data.username,
            "created_at": data.created_at.isoformat() if data.created_at else None,
        }
    )


def _deserialize(raw: str) -> SessionData:
    d = json.loads(raw)
    created = d.get("created_at")
    return SessionData(
        base_url=d["base_url"],
        client_id=d["client_id"],
        cookies=d["cookies"],
        username=d.get("username"),
        created_at=datetime.fromisoformat(created) if created else None,
    )


class SessionStore(ABC):
    """Interface für Session-Speicher."""

    @abstractmethod
    def save(self, data: SessionData) -> None: ...

    @abstractmethod
    def load(self) -> SessionData | None: ...

    @abstractmethod
    def delete(self) -> None: ...


class InMemorySessionStore(SessionStore):
    """In-Memory-Store (für Tests)."""

    def __init__(self) -> None:
        self._data: SessionData | None = None

    def save(self, data: SessionData) -> None:
        self._data = data

    def load(self) -> SessionData | None:
        return self._data

    def delete(self) -> None:
        self._data = None


def _is_fail_backend(backend: object) -> bool:
    cls = type(backend)
    return "fail" in cls.__module__.lower()


class KeyringSessionStore(SessionStore):
    """Speichert die Session als JSON im OS-Schlüsselbund (keyring)."""

    def __init__(self, keyring_module=None) -> None:
        if keyring_module is None:
            try:
                import keyring
            except ImportError as exc:
                raise KeyringUnavailableError(
                    "Das Paket 'keyring' ist nicht installiert"
                ) from exc
            keyring_module = keyring
        self._keyring = keyring_module
        try:
            backend = keyring_module.get_keyring()
        except Exception as exc:
            raise KeyringUnavailableError(
                f"Kein Keyring-Backend verfügbar: {exc}"
            ) from exc
        if _is_fail_backend(backend):
            raise KeyringUnavailableError("Kein Keyring-Backend verfügbar")

    def save(self, data: SessionData) -> None:
        self._keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, _serialize(data))

    def load(self) -> SessionData | None:
        raw = self._keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
        if raw is None:
            return None
        return _deserialize(raw)

    def delete(self) -> None:
        try:
            self._keyring.delete_password(KEYRING_SERVICE, KEYRING_KEY)
        except Exception:
            pass


class FileSessionStore(SessionStore):
    """Datei-Fallback mit Rechten 0600 (wenn kein Keyring verfügbar ist)."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def save(self, data: SessionData) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(_serialize(data))
        os.chmod(self._path, 0o600)

    def load(self) -> SessionData | None:
        if not self._path.exists():
            return None
        return _deserialize(self._path.read_text())

    def delete(self) -> None:
        self._path.unlink(missing_ok=True)


def default_store(config: Config) -> SessionStore:
    """Keyring wenn verfügbar, sonst Datei-Fallback (0600)."""
    try:
        return KeyringSessionStore()
    except KeyringUnavailableError:
        return FileSessionStore(config.session_path)
