"""Session storage with keyring and file fallback."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import keyring
from keyring.errors import KeyringError, NoKeyringError

from ilias_core.config import Config
from ilias_core.errors import ILIASError
from ilias_core.models import SessionCookies

# Allow injecting custom keyring functions for testing
_keyring_set_password: Callable[[str, str, str], None] = keyring.set_password
_keyring_get_password: Callable[[str, str], str | None] = keyring.get_password
_keyring_delete_password: Callable[[str, str], None] = keyring.delete_password
_keyring_get_keyring: Callable[[], Any] = keyring.get_keyring


def _set_keyring_backend(
    set_password: Callable[[str, str, str], None] | None = None,
    get_password: Callable[[str, str], str | None] | None = None,
    delete_password: Callable[[str, str], None] | None = None,
    get_keyring: Callable[[], Any] | None = None,
) -> None:
    """Set custom keyring backend (for testing)."""
    global _keyring_set_password, _keyring_get_password, _keyring_delete_password, _keyring_get_keyring
    if set_password is not None:
        _keyring_set_password = set_password
    if get_password is not None:
        _keyring_get_password = get_password
    if delete_password is not None:
        _keyring_delete_password = delete_password
    if get_keyring is not None:
        _keyring_get_keyring = get_keyring


def _reset_keyring_backend() -> None:
    """Reset to default keyring backend."""
    global _keyring_set_password, _keyring_get_password, _keyring_delete_password, _keyring_get_keyring
    _keyring_set_password = keyring.set_password
    _keyring_get_password = keyring.get_password
    _keyring_delete_password = keyring.delete_password
    _keyring_get_keyring = keyring.get_keyring


class SessionStore(ABC):
    """Abstract session store interface."""

    @abstractmethod
    def save(self, cookies: SessionCookies) -> None:
        """Save session cookies."""

    @abstractmethod
    def load(self) -> SessionCookies | None:
        """Load session cookies, return None if not found."""

    @abstractmethod
    def delete(self) -> None:
        """Delete stored session."""


class KeyringSessionStore(SessionStore):
    """Session store using OS keyring."""

    SERVICE_NAME = "ilias-cli"
    USERNAME_KEY = "session"

    def __init__(self, config: Config) -> None:
        self.config = config

    def save(self, cookies: SessionCookies) -> None:
        data = json.dumps(cookies.to_dict())
        try:
            _keyring_set_password(self.SERVICE_NAME, self.USERNAME_KEY, data)
        except KeyringError as e:
            raise ILIASError(f"Failed to save session to keyring: {e}") from e

    def load(self) -> SessionCookies | None:
        try:
            data = _keyring_get_password(self.SERVICE_NAME, self.USERNAME_KEY)
            if data is None:
                return None
            return SessionCookies.from_dict(json.loads(data))
        except KeyringError:
            return None
        except (json.JSONDecodeError, KeyError):
            return None

    def delete(self) -> None:
        try:
            _keyring_delete_password(self.SERVICE_NAME, self.USERNAME_KEY)
        except KeyringError:
            pass  # Ignore if not found


class FileSessionStore(SessionStore):
    """Session store using a file with 0600 permissions."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.session_file = config.session_file

    def _ensure_dir(self) -> None:
        self.session_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(self, cookies: SessionCookies) -> None:
        self._ensure_dir()
        data = json.dumps(cookies.to_dict(), indent=2)
        try:
            # Write with 0600 permissions
            with os.fdopen(os.open(self.session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                f.write(data)
        except OSError as e:
            raise ILIASError(f"Failed to save session to file: {e}") from e

    def load(self) -> SessionCookies | None:
        try:
            with self.session_file.open("r") as f:
                data = json.load(f)
            return SessionCookies.from_dict(data)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None
        except OSError:
            return None

    def delete(self) -> None:
        try:
            self.session_file.unlink(missing_ok=True)
        except OSError:
            pass


def create_session_store(config: Config) -> SessionStore:
    """Create appropriate session store based on config and availability."""
    if config.session_store == "keyring":
        return KeyringSessionStore(config)
    elif config.session_store == "file":
        return FileSessionStore(config)

    # Auto: try keyring first, fallback to file
    try:
        _keyring_get_keyring()
        # Test if keyring works
        test_service = f"{KeyringSessionStore.SERVICE_NAME}-test"
        _keyring_set_password(test_service, "test", "test")
        _keyring_delete_password(test_service, "test")
        return KeyringSessionStore(config)
    except (NoKeyringError, KeyringError, OSError):
        return FileSessionStore(config)