"""Tests for session storage."""

import json
import os
import stat
from pathlib import Path

import pytest

from ilias_core.config import Config
from ilias_core.models import SessionCookies
from ilias_core.session import FileSessionStore, KeyringSessionStore, create_session_store
from ilias_core.errors import ILIASError


class TestFileSessionStore:
    """Tests for file-based session store."""

    def test_save_and_load(self, file_session_store: FileSessionStore, session_cookies: SessionCookies) -> None:
        """Test saving and loading session cookies."""
        file_session_store.save(session_cookies)
        loaded = file_session_store.load()

        assert loaded is not None
        assert loaded.phpsessid == session_cookies.phpsessid
        assert loaded.il_client_id == session_cookies.il_client_id
        assert loaded.extra == session_cookies.extra

    def test_load_nonexistent(self, file_session_store: FileSessionStore) -> None:
        """Test loading when no session exists."""
        loaded = file_session_store.load()
        assert loaded is None

    def test_delete(self, file_session_store: FileSessionStore, session_cookies: SessionCookies) -> None:
        """Test deleting session."""
        file_session_store.save(session_cookies)
        file_session_store.delete()
        loaded = file_session_store.load()
        assert loaded is None

    def test_file_permissions_0600(self, file_session_store: FileSessionStore, session_cookies: SessionCookies) -> None:
        """Test session file has 0600 permissions."""
        file_session_store.save(session_cookies)
        session_file = file_session_store.session_file

        assert session_file.exists()
        file_stat = session_file.stat()
        # Check permissions are 0600 (owner read/write only)
        assert stat.S_IMODE(file_stat.st_mode) == 0o600

    def test_corrupted_file(self, file_session_store: FileSessionStore) -> None:
        """Test loading corrupted session file returns None."""
        file_session_store.session_file.write_text("not json")
        loaded = file_session_store.load()
        assert loaded is None


class TestKeyringSessionStore:
    """Tests for keyring-based session store."""

    def test_save_and_load(self, keyring_session_store: KeyringSessionStore, session_cookies: SessionCookies) -> None:
        """Test saving and loading session cookies."""
        keyring_session_store.save(session_cookies)
        loaded = keyring_session_store.load()

        assert loaded is not None
        assert loaded.phpsessid == session_cookies.phpsessid
        assert loaded.il_client_id == session_cookies.il_client_id

    def test_load_nonexistent(self, keyring_session_store: KeyringSessionStore) -> None:
        """Test loading when no session exists."""
        loaded = keyring_session_store.load()
        assert loaded is None

    def test_delete(self, keyring_session_store: KeyringSessionStore, session_cookies: SessionCookies) -> None:
        """Test deleting session."""
        keyring_session_store.save(session_cookies)
        keyring_session_store.delete()
        loaded = keyring_session_store.load()
        assert loaded is None


class TestCreateSessionStore:
    """Tests for session store factory."""

    def test_create_file_store_explicit(self, test_config: Config) -> None:
        """Test explicit file store creation."""
        test_config.session_store = "file"
        store = create_session_store(test_config)
        assert isinstance(store, FileSessionStore)

    def test_create_keyring_store_explicit(self, test_config: Config, mock_keyring: None) -> None:
        """Test explicit keyring store creation."""
        test_config.session_store = "keyring"
        store = create_session_store(test_config)
        assert isinstance(store, KeyringSessionStore)

    def test_create_auto_fallback_to_file(self, test_config: Config) -> None:
        """Test auto mode falls back to file when keyring unavailable."""
        test_config.session_store = "auto"
        store = create_session_store(test_config)
        assert isinstance(store, FileSessionStore)