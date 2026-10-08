"""Tests für Session-Stores, SessionManager und Gültigkeitsprüfung."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone

import httpx
import pytest

from ilias_core.config import Config
from ilias_core.errors import NotAuthenticatedError
from ilias_core.models import LoginResult, SessionData
from ilias_core.session.manager import SessionManager, check_session
from ilias_core.session.store import (
    FileSessionStore,
    InMemorySessionStore,
    KeyringSessionStore,
    default_store,
)

from conftest import BASE_URL, CLIENT_ID


def _session_data() -> SessionData:
    return SessionData(
        base_url=BASE_URL,
        client_id=CLIENT_ID,
        cookies={"PHPSESSID": "abc", "ilClientId": CLIENT_ID},
        username="testuser",
        created_at=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
    )


class FakeKeyring:
    """In-Memory-Ersatz für das keyring-Modul."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_keyring(self):
        return self

    def set_password(self, service, key, value):
        self._store[(service, key)] = value

    def get_password(self, service, key):
        return self._store.get((service, key))

    def delete_password(self, service, key):
        self._store.pop((service, key), None)


def test_file_store_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "session.json"
    store = FileSessionStore(path)
    data = _session_data()
    store.save(data)

    assert path.exists()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600

    loaded = store.load()
    assert loaded is not None
    assert loaded.cookies == data.cookies
    assert loaded.username == "testuser"
    assert loaded.created_at == data.created_at

    store.delete()
    assert not path.exists()
    assert store.load() is None


def test_file_store_load_missing_returns_none(tmp_path):
    store = FileSessionStore(tmp_path / "nope.json")
    assert store.load() is None


def test_in_memory_store():
    store = InMemorySessionStore()
    assert store.load() is None
    data = _session_data()
    store.save(data)
    assert store.load() == data
    store.delete()
    assert store.load() is None


def test_keyring_store_with_in_memory_backend():
    fake = FakeKeyring()
    store = KeyringSessionStore(keyring_module=fake)
    data = _session_data()
    store.save(data)

    loaded = store.load()
    assert loaded is not None
    assert loaded.cookies == data.cookies

    store.delete()
    assert store.load() is None


def test_keyring_store_rejects_fail_backend():
    class FailBackend:
        pass

    FailBackend.__module__ = "keyring.backends.fail"

    class FailKeyring:
        def get_keyring(self):
            return FailBackend()

    from ilias_core.errors import KeyringUnavailableError

    with pytest.raises(KeyringUnavailableError):
        KeyringSessionStore(keyring_module=FailKeyring())


def test_default_store_falls_back_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ilias_core.session.store.KeyringSessionStore",
        lambda *a, **k: (_ for _ in ()).throw(
            __import__("ilias_core.errors", fromlist=["KeyringUnavailableError"]).KeyringUnavailableError("no backend")
        ),
    )
    config = Config(base_url=BASE_URL, client_id=CLIENT_ID, config_path=tmp_path / "c.toml")
    store = default_store(config)
    assert isinstance(store, FileSessionStore)


def _client_returning(response: httpx.Response) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_check_session_logged_in(html):
    client = _client_returning(httpx.Response(200, html=html["dashboard"]))
    status = check_session(BASE_URL, CLIENT_ID, {"PHPSESSID": "abc"}, client=client)
    assert status.logged_in is True
    assert status.base_url == BASE_URL


def test_check_session_expired_redirect(html):
    from urllib.parse import urlparse

    def handler(request: httpx.Request) -> httpx.Response:
        if urlparse(str(request.url)).path == "/login.php":
            return httpx.Response(200, html=html["login_page"])
        return httpx.Response(
            302, headers={"location": f"{BASE_URL}/login.php?client_id=iliashhn"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    status = check_session(BASE_URL, CLIENT_ID, {"PHPSESSID": "expired"}, client=client)
    assert status.logged_in is False
    assert "abgelaufen" in status.message.lower()


def test_check_session_expired_login_form(html):
    client = _client_returning(httpx.Response(200, html=html["login_page"]))
    status = check_session(BASE_URL, CLIENT_ID, {}, client=client)
    assert status.logged_in is False


def test_manager_check_without_session_raises(memory_store):
    config = Config(base_url=BASE_URL, client_id=CLIENT_ID)
    manager = SessionManager(config, store=memory_store)
    with pytest.raises(NotAuthenticatedError) as exc_info:
        manager.check()
    assert exc_info.value.exit_code == 2


def test_manager_save_and_check(memory_store, html):
    config = Config(base_url=BASE_URL, client_id=CLIENT_ID)
    manager = SessionManager(config, store=memory_store)
    manager.save(
        LoginResult(cookies={"PHPSESSID": "abc", "ilClientId": CLIENT_ID}),
        username="testuser",
    )
    data = manager.load()
    assert data is not None
    assert data.cookies["PHPSESSID"] == "abc"
    assert data.username == "testuser"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html["dashboard"])

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    from ilias_core.session.manager import check_session

    status = check_session(data.base_url, data.client_id, data.cookies, client=client)
    assert status.logged_in is True


def test_manager_delete(memory_store):
    config = Config(base_url=BASE_URL, client_id=CLIENT_ID)
    manager = SessionManager(config, store=memory_store)
    manager.save(LoginResult(cookies={"PHPSESSID": "abc"}))
    assert manager.load() is not None
    manager.delete()
    assert manager.load() is None
