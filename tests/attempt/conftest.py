"""Pytest configuration and shared fixtures."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock, MagicMock

import httpx
import keyring
import pytest
import respx
from keyring.backends.null import Keyring as NullKeyring

from ilias_core.session import _set_keyring_backend, _reset_keyring_backend


class InMemoryKeyring:
    """In-memory keyring backend for testing."""

    def __init__(self) -> None:
        self._storage: Dict[str, Dict[str, str]] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        if service not in self._storage:
            self._storage[service] = {}
        self._storage[service][username] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._storage.get(service, {}).get(username)

    def delete_password(self, service: str, username: str) -> None:
        if service in self._storage:
            self._storage[service].pop(username, None)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    """Create temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_config_dir: Path):
    """Create test configuration."""
    from ilias_core.config import Config
    config = Config()
    config.config_dir = temp_config_dir
    config.base_url = "https://ilias.test.de"
    config.client_id = "iliastest"
    config.timeout = 5.0
    return config


@pytest.fixture
def mock_keyring() -> Generator[InMemoryKeyring, None, None]:
    """Replace keyring with in-memory backend for tests."""
    in_memory_keyring = InMemoryKeyring()
    _set_keyring_backend(
        set_password=in_memory_keyring.set_password,
        get_password=in_memory_keyring.get_password,
        delete_password=in_memory_keyring.delete_password,
        get_keyring=lambda: in_memory_keyring,
    )
    yield in_memory_keyring
    _reset_keyring_backend()


@pytest.fixture
def session_cookies():
    """Create test session cookies."""
    from ilias_core.models import SessionCookies
    return SessionCookies(
        phpsessid="test_phpsessid_123",
        il_client_id="test_ilclient_456",
        extra={"other_cookie": "value"},
    )


@pytest.fixture
def file_session_store(test_config):
    """Create file session store for tests."""
    from ilias_core.session import FileSessionStore
    return FileSessionStore(test_config)


@pytest.fixture
def keyring_session_store(test_config, mock_keyring):
    """Create keyring session store for tests."""
    from ilias_core.session import KeyringSessionStore
    return KeyringSessionStore(test_config)


@pytest.fixture
def login_html() -> str:
    """Load Keycloak login form HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "keycloak_login.html"
    return fixture_path.read_text()


@pytest.fixture
def login_error_html() -> str:
    """Load Keycloak login error HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "keycloak_login_error.html"
    return fixture_path.read_text()


@pytest.fixture
def totp_html() -> str:
    """Load Keycloak TOTP form HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "keycloak_totp.html"
    return fixture_path.read_text()


@pytest.fixture
def totp_error_html() -> str:
    """Load Keycloak TOTP error HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "keycloak_totp_error.html"
    return fixture_path.read_text()


@pytest.fixture
def dashboard_html() -> str:
    """Load ILIAS dashboard HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "ilias_dashboard.html"
    return fixture_path.read_text()


@pytest.fixture
def login_redirect_html() -> str:
    """Load ILIAS login redirect HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "ilias_login_redirect.html"
    return fixture_path.read_text()


@pytest.fixture
def unexpected_html() -> str:
    """Load unexpected HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "unexpected.html"
    return fixture_path.read_text()


@pytest.fixture
def mock_httpx() -> Generator[respx.MockRouter, None, None]:
    """Mock httpx with respx."""
    with respx.mock(assert_all_called=False) as router:
        yield router


class MockAsyncClient:
    """Mock httpx.AsyncClient for testing without network."""

    def __init__(self, responses: Dict[str, httpx.Response]):
        self.responses = responses
        self.requests = []

    async def get(self, url: str, **kwargs) -> httpx.Response:
        self.requests.append(("GET", url, kwargs))
        if url in self.responses:
            return self.responses[url]
        return httpx.Response(404, text="Not Found")

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.requests.append(("POST", url, kwargs))
        if url in self.responses:
            return self.responses[url]
        return httpx.Response(404, text="Not Found")

    async def aclose(self) -> None:
        pass

    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, *args):
        pass

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_client_factory():
    """Factory for creating mock clients."""
    def create(responses: Dict[str, httpx.Response]) -> MockAsyncClient:
        return MockAsyncClient(responses)
    return create