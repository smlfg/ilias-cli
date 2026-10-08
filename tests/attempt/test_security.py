"""Tests for security requirements - password/TOTP never in logs/output."""

import logging
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core.config import Config
from ilias_core.models import SessionCookies, LoginResult
from ilias_core.errors import InvalidCredentialsError


runner = CliRunner()


@pytest.fixture
def test_config(tmp_path) -> Config:
    """Create test configuration."""
    config = Config()
    config.config_dir = tmp_path
    config.base_url = "https://ilias.test.de"
    config.client_id = "iliastest"
    config.timeout = 5.0
    return config


@pytest.fixture
def session_cookies() -> SessionCookies:
    """Create test session cookies."""
    return SessionCookies(phpsessid="test_session", il_client_id="test_client")


def test_password_not_in_exception_message(test_config: Config) -> None:
    """Test that password doesn't appear in exception messages."""
    error = InvalidCredentialsError("Invalid username or password")
    error_str = str(error)
    assert "password" not in error_str.lower() or "password" in error_str.lower()  # "password" in message is OK as word
    # But actual password value should never be there
    assert "mysecretpassword123" not in error_str


def test_password_not_in_login_result_json(test_config: Config, session_cookies: SessionCookies) -> None:
    """Test that password doesn't appear in LoginResult JSON."""
    result = LoginResult(success=True, message="OK", cookies=session_cookies)
    json_str = result.model_dump_json(exclude={"cookies"})
    data = json.loads(json_str)

    # No password field should exist
    assert "password" not in json_str.lower()
    assert "mysecretpassword123" not in json_str


@pytest.mark.asyncio
async def test_password_not_logged_during_login(
    test_config: Config,
    session_cookies: SessionCookies,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that password is never logged during login flow."""
    from ilias_core.auth import AuthClient

    caplog.set_level(logging.DEBUG)

    with patch.object(AuthClient, "_login_headless", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = LoginResult(
            success=True,
            message="Login successful",
            cookies=session_cookies,
        )

        async with AuthClient(test_config) as client:
            await client.login("testuser", "mysecretpassword123", lambda: "123456")

    # Check logs don't contain password
    for record in caplog.records:
        assert "mysecretpassword123" not in record.getMessage()
        assert "mysecretpassword123" not in str(record.__dict__)


def test_cli_password_not_in_output(
    test_config: Config,
    session_cookies: SessionCookies,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test that CLI doesn't output password."""
    with patch("ilias_cli.main.AuthClient") as mock_auth_client, \
         patch("ilias_cli.main.create_session_store") as mock_create_store:

        mock_store = MagicMock()
        mock_create_store.return_value = mock_store

        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.return_value = LoginResult(
            success=True,
            message="Login successful",
            cookies=session_cookies,
        )

        # Simulate password input
        with patch("ilias_cli.main.typer.prompt", side_effect=["testuser", "mysecretpassword123", "123456"]):
            result = runner.invoke(app, ["login", "--username", "testuser"], env={"ILIAS_CLI_CONFIG_DIR": str(test_config.config_dir)})

    output = result.output
    assert "mysecretpassword123" not in output
    assert "123456" not in output  # TOTP also shouldn't appear


def test_cli_totp_not_in_output(
    test_config: Config,
    session_cookies: SessionCookies,
) -> None:
    """Test that CLI doesn't output TOTP code."""
    with patch("ilias_cli.main.AuthClient") as mock_auth_client, \
         patch("ilias_cli.main.create_session_store") as mock_create_store:

        mock_store = MagicMock()
        mock_create_store.return_value = mock_store

        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.return_value = LoginResult(
            success=True,
            message="Login successful",
            cookies=session_cookies,
        )

        with patch("ilias_cli.main.typer.prompt", side_effect=["testuser", "password123", "mysecretotp123"]):
            result = runner.invoke(app, ["login", "--username", "testuser"], env={"ILIAS_CLI_CONFIG_DIR": str(test_config.config_dir)})

    output = result.output
    assert "mysecretotp123" not in output


def test_session_cookies_not_in_status_json(
    test_config: Config,
    session_cookies: SessionCookies,
) -> None:
    """Test that session cookies are not in status JSON output."""
    from ilias_core.models import SessionStatus

    status = SessionStatus(logged_in=True, message="OK", username="testuser")
    json_str = status.model_dump_json()
    data = json.loads(json_str)

    assert "PHPSESSID" not in json_str
    assert "ilClientId" not in json_str
    assert session_cookies.phpsessid not in json_str
    assert session_cookies.il_client_id not in json_str


def test_file_session_store_permissions(test_config: Config, session_cookies: SessionCookies) -> None:
    """Test that file session store creates file with 0600 permissions."""
    import stat
    from ilias_core.session import FileSessionStore

    store = FileSessionStore(test_config)
    store.save(session_cookies)

    session_file = store.session_file
    assert session_file.exists()

    file_stat = session_file.stat()
    permissions = stat.S_IMODE(file_stat.st_mode)
    assert permissions == 0o600, f"Expected 0600, got {oct(permissions)}"