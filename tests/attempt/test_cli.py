"""Tests for CLI commands."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core.config import Config
from ilias_core.models import SessionCookies, LoginResult, SessionStatus, LogoutResult
from ilias_core.errors import InvalidCredentialsError, InvalidTOTPError, NetworkError
from ilias_core.session import FileSessionStore


runner = CliRunner()


@pytest.fixture
def temp_config_dir() -> Path:
    """Create temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_config_dir: Path) -> Config:
    """Create test configuration."""
    config = Config()
    config.config_dir = temp_config_dir
    config.base_url = "https://ilias.test.de"
    config.client_id = "iliastest"
    config.timeout = 5.0
    return config


@pytest.fixture
def session_cookies() -> SessionCookies:
    """Create test session cookies."""
    return SessionCookies(phpsessid="test_session", il_client_id="test_client")


def invoke_cli(args: list[str], config: Config, env: dict | None = None) -> tuple[int, str]:
    """Invoke CLI command with config."""
    config_path = config.config_dir / "config.toml"
    config_path.write_text(f"""
base_url = "{config.base_url}"
client_id = "{config.client_id}"
""")
    cmd_env = {"ILIAS_CLI_CONFIG_DIR": str(config.config_dir)}
    if env:
        cmd_env.update(env)
    result = runner.invoke(app, args, env=cmd_env)
    return result.exit_code, result.output


class TestLoginCommand:
    """Tests for login command."""

    def test_login_requires_username_or_prompt(self, test_config: Config) -> None:
        """Test login fails without username in JSON mode."""
        exit_code, output = invoke_cli(["--json", "login"], test_config)
        assert exit_code == 1
        data = json.loads(output)
        assert "error" in data
        assert "Username required" in data["error"]

    @patch("ilias_cli.main.AuthClient")
    @patch("ilias_cli.main.create_session_store")
    def test_login_success(
        self,
        mock_create_store,
        mock_auth_client,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test successful login."""
        # Setup mocks
        mock_store = MagicMock()
        mock_store.load.return_value = None  # Not logged in
        mock_create_store.return_value = mock_store

        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.return_value = LoginResult(
            success=True,
            message="Login successful",
            cookies=session_cookies,
        )

        # Use CliRunner with input for prompts
        config_path = test_config.config_dir / "config.toml"
        config_path.write_text(f"""
base_url = "{test_config.base_url}"
client_id = "{test_config.client_id}"
""")
        cmd_env = {"ILIAS_CLI_CONFIG_DIR": str(test_config.config_dir)}
        # Input: password, totp
        result = runner.invoke(app, ["login", "--username", "testuser"], env=cmd_env, input="password123\n123456\n")

        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "Login Successful" in result.output
        mock_store.save.assert_called_once_with(session_cookies)

    @patch("ilias_cli.main.AuthClient")
    def test_login_invalid_credentials(
        self,
        mock_auth_client,
        test_config: Config,
    ) -> None:
        """Test login with invalid credentials."""
        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.side_effect = InvalidCredentialsError("Invalid username or password")

        with patch("ilias_cli.main.typer.prompt", side_effect=["testuser", "wrongpass", "123456"]):
            exit_code, output = invoke_cli(["login", "--username", "testuser"], test_config)

        assert exit_code == 1
        assert "Invalid username or password" in output

    @patch("ilias_cli.main.AuthClient")
    def test_login_invalid_totp(
        self,
        mock_auth_client,
        test_config: Config,
    ) -> None:
        """Test login with invalid TOTP."""
        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.side_effect = InvalidTOTPError("Invalid TOTP code")

        with patch("ilias_cli.main.typer.prompt", side_effect=["testuser", "password123", "000000"]):
            exit_code, output = invoke_cli(["login", "--username", "testuser"], test_config)

        assert exit_code == 1
        assert "Invalid TOTP code" in output

    @patch("ilias_cli.main.AuthClient")
    def test_login_network_error(
        self,
        mock_auth_client,
        test_config: Config,
    ) -> None:
        """Test login with network error."""
        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.side_effect = NetworkError("Connection failed")

        with patch("ilias_cli.main.typer.prompt", side_effect=["testuser", "password123", "123456"]):
            exit_code, output = invoke_cli(["login", "--username", "testuser"], test_config)

        assert exit_code == 4

    @patch("ilias_cli.main.AuthClient")
    def test_login_json_output(
        self,
        mock_auth_client,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test login with --json output."""
        mock_client = AsyncMock()
        mock_auth_client.return_value.__aenter__.return_value = mock_client
        mock_client.login.return_value = LoginResult(
            success=True,
            message="Login successful",
            cookies=session_cookies,
        )

        # In JSON mode, prompts won't work, so we expect an error
        exit_code, output = invoke_cli(["--json", "login", "--username", "testuser"], test_config)
        assert exit_code == 1
        data = json.loads(output)
        assert "error" in data
        assert "Password input not supported in JSON mode" in data["error"]


class TestStatusCommand:
    """Tests for status command."""

    @patch("ilias_cli.main.create_session_store")
    def test_status_not_logged_in(
        self,
        mock_create_store,
        test_config: Config,
    ) -> None:
        """Test status when not logged in."""
        mock_store = MagicMock()
        mock_store.load.return_value = None
        mock_create_store.return_value = mock_store

        exit_code, output = invoke_cli(["status"], test_config)

        assert exit_code == 2
        assert "Not logged in" in output

    @patch("ilias_cli.main.create_session_store")
    @patch("ilias_cli.main.check_session_status")
    def test_status_logged_in(
        self,
        mock_check_status,
        mock_create_store,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test status when logged in."""
        mock_store = MagicMock()
        mock_store.load.return_value = session_cookies
        mock_create_store.return_value = mock_store

        mock_check_status.return_value = SessionStatus(
            logged_in=True,
            message="Session valid",
            username="testuser",
        )

        exit_code, output = invoke_cli(["status"], test_config)

        assert exit_code == 0
        assert "Logged in" in output
        assert "testuser" in output

    @patch("ilias_cli.main.create_session_store")
    @patch("ilias_cli.main.check_session_status")
    def test_status_expired(
        self,
        mock_check_status,
        mock_create_store,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test status when session expired."""
        mock_store = MagicMock()
        mock_store.load.return_value = session_cookies
        mock_create_store.return_value = mock_store

        mock_check_status.return_value = SessionStatus(
            logged_in=False,
            message="Session expired",
        )

        exit_code, output = invoke_cli(["status"], test_config)

        assert exit_code == 3
        assert "Session expired" in output

    @patch("ilias_cli.main.create_session_store")
    @patch("ilias_cli.main.check_session_status")
    def test_status_json_output(
        self,
        mock_check_status,
        mock_create_store,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test status with --json output."""
        mock_store = MagicMock()
        mock_store.load.return_value = session_cookies
        mock_create_store.return_value = mock_store

        mock_check_status.return_value = SessionStatus(
            logged_in=True,
            message="Session valid",
            username="testuser",
        )

        exit_code, output = invoke_cli(["--json", "status"], test_config)

        assert exit_code == 0
        data = json.loads(output)
        assert data["logged_in"] is True
        assert data["username"] == "testuser"
        # Ensure no cookies in output
        assert "cookies" not in data


class TestLogoutCommand:
    """Tests for logout command."""

    @patch("ilias_cli.main.create_session_store")
    def test_logout_not_logged_in(
        self,
        mock_create_store,
        test_config: Config,
    ) -> None:
        """Test logout when not logged in."""
        mock_store = MagicMock()
        mock_store.load.return_value = None
        mock_create_store.return_value = mock_store

        exit_code, output = invoke_cli(["logout"], test_config)

        assert exit_code == 0
        assert "Not logged in" in output

    @patch("ilias_cli.main.create_session_store")
    def test_logout_success(
        self,
        mock_create_store,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test successful logout."""
        mock_store = MagicMock()
        mock_store.load.return_value = session_cookies
        mock_create_store.return_value = mock_store

        exit_code, output = invoke_cli(["logout"], test_config)

        assert exit_code == 0
        assert "Logged out successfully" in output
        mock_store.delete.assert_called_once()

    @patch("ilias_cli.main.create_session_store")
    def test_logout_json_output(
        self,
        mock_create_store,
        test_config: Config,
        session_cookies: SessionCookies,
    ) -> None:
        """Test logout with --json output."""
        mock_store = MagicMock()
        mock_store.load.return_value = session_cookies
        mock_create_store.return_value = mock_store

        exit_code, output = invoke_cli(["--json", "logout"], test_config)

        assert exit_code == 0
        data = json.loads(output)
        assert data["success"] is True
        assert data["message"] == "Logged out successfully"


class TestConfigShowCommand:
    """Tests for config show command."""

    def test_config_show(self, test_config: Config) -> None:
        """Test config show command."""
        exit_code, output = invoke_cli(["config-show"], test_config)

        assert exit_code == 0
        assert "https://ilias.test.de" in output
        assert "iliastest" in output

    def test_config_show_json(self, test_config: Config) -> None:
        """Test config show with --json."""
        exit_code, output = invoke_cli(["--json", "config-show"], test_config)

        assert exit_code == 0
        data = json.loads(output)
        assert data["base_url"] == "https://ilias.test.de"
        assert data["client_id"] == "iliastest"