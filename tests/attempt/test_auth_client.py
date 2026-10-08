"""Tests for AuthClient login flow."""

import asyncio
import httpx
import pytest
import respx

from ilias_core.config import Config
from ilias_core.auth import AuthClient, check_session_status
from ilias_core.models import SessionCookies, SessionStatus
from ilias_core.errors import (
    InvalidCredentialsError,
    InvalidTOTPError,
    ParserError,
    NetworkError,
    BrowserNotAvailableError,
)
from ilias_core.session import FileSessionStore


@pytest.fixture
def test_config() -> Config:
    """Create test configuration."""
    config = Config()
    config.base_url = "https://ilias.test.de"
    config.client_id = "iliastest"
    config.timeout = 5.0
    return config


@pytest.fixture
def login_form_html() -> str:
    """Load login form fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/keycloak_login.html").read_text()


@pytest.fixture
def login_error_html() -> str:
    """Load login error fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/keycloak_login_error.html").read_text()


@pytest.fixture
def totp_form_html() -> str:
    """Load TOTP form fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/keycloak_totp.html").read_text()


@pytest.fixture
def totp_error_html() -> str:
    """Load TOTP error fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/keycloak_totp_error.html").read_text()


@pytest.fixture
def dashboard_html() -> str:
    """Load dashboard fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/ilias_dashboard.html").read_text()


@pytest.fixture
def login_redirect_html() -> str:
    """Load login redirect fixture."""
    from pathlib import Path
    return Path(__file__).parent.joinpath("fixtures/ilias_login_redirect.html").read_text()


class TestAuthClientLogin:
    """Tests for AuthClient.login() method."""

    @pytest.mark.asyncio
    async def test_successful_login_without_totp(
        self,
        test_config: Config,
        login_form_html: str,
        dashboard_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test successful login without TOTP."""
        # Mock the flow: openidconnect -> login form -> post credentials -> dashboard with cookies
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(200, text=login_form_html)
        )
        # POST to Keycloak
        respx_mock.post(
            "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
        ).mock(
            return_value=httpx.Response(
                200,
                text=dashboard_html,
                headers={"Set-Cookie": "PHPSESSID=session123; Path=/; HttpOnly, ilClientId=client456; Path=/; HttpOnly"},
            )
        )

        totp_called = False

        def totp_callback() -> str:
            nonlocal totp_called
            totp_called = True
            return "123456"

        async with AuthClient(test_config) as client:
            result = await client.login("testuser", "password123", totp_callback)

        assert result.success is True
        assert result.cookies is not None
        assert result.cookies.phpsessid == "session123"
        assert result.cookies.il_client_id == "client456"
        assert not totp_called  # TOTP not needed

    @pytest.mark.asyncio
    async def test_successful_login_with_totp(
        self,
        test_config: Config,
        login_form_html: str,
        totp_form_html: str,
        dashboard_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test successful login with TOTP."""
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(200, text=login_form_html)
        )
        # First POST - credentials
        respx_mock.post(
            "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
        ).mock(
            side_effect=[
                httpx.Response(200, text=totp_form_html),  # First POST -> TOTP form
                httpx.Response(
                    200,
                    text=dashboard_html,
                    headers={"Set-Cookie": "PHPSESSID=session123; Path=/; HttpOnly, ilClientId=client456; Path=/; HttpOnly"},
                ),  # Second POST (TOTP) -> dashboard
            ]
        )

        totp_called = False

        def totp_callback() -> str:
            nonlocal totp_called
            totp_called = True
            return "123456"

        async with AuthClient(test_config) as client:
            result = await client.login("testuser", "password123", totp_callback)

        assert result.success is True
        assert result.cookies is not None
        assert totp_called is True

    @pytest.mark.asyncio
    async def test_invalid_credentials(
        self,
        test_config: Config,
        login_form_html: str,
        login_error_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test login with invalid credentials."""
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(200, text=login_form_html)
        )
        respx_mock.post(
            "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
        ).mock(
            return_value=httpx.Response(200, text=login_error_html)
        )

        def totp_callback() -> str:
            return "123456"

        async with AuthClient(test_config) as client:
            with pytest.raises(InvalidCredentialsError):
                await client.login("testuser", "wrongpassword", totp_callback)

    @pytest.mark.asyncio
    async def test_invalid_totp(
        self,
        test_config: Config,
        login_form_html: str,
        totp_form_html: str,
        totp_error_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test login with invalid TOTP."""
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(200, text=login_form_html)
        )
        respx_mock.post(
            "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
        ).mock(
            side_effect=[
                httpx.Response(200, text=totp_form_html),  # First POST -> TOTP form
                httpx.Response(200, text=totp_error_html),  # TOTP POST -> error
            ]
        )

        def totp_callback() -> str:
            return "000000"

        async with AuthClient(test_config) as client:
            with pytest.raises(InvalidTOTPError):
                await client.login("testuser", "password123", totp_callback)

    @pytest.mark.asyncio
    async def test_unexpected_html_parser_error(
        self,
        test_config: Config,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test unexpected HTML raises ParserError."""
        unexpected_html = "<html><body>Unexpected</body></html>"
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(200, text=unexpected_html)
        )

        def totp_callback() -> str:
            return "123456"

        async with AuthClient(test_config) as client:
            with pytest.raises(ParserError):
                await client.login("testuser", "password123", totp_callback)

    @pytest.mark.asyncio
    async def test_network_error(
        self,
        test_config: Config,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test network error raises NetworkError."""
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        def totp_callback() -> str:
            return "123456"

        async with AuthClient(test_config) as client:
            with pytest.raises(NetworkError):
                await client.login("testuser", "password123", totp_callback)

    @pytest.mark.asyncio
    async def test_http_status_error(
        self,
        test_config: Config,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test HTTP error status raises NetworkError."""
        respx_mock.get("https://ilias.test.de/openidconnect.php").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        def totp_callback() -> str:
            return "123456"

        async with AuthClient(test_config) as client:
            with pytest.raises(NetworkError) as exc_info:
                await client.login("testuser", "password123", totp_callback)
            assert "500" in str(exc_info.value)


class TestCheckSessionStatus:
    """Tests for check_session_status function."""

    @pytest.mark.asyncio
    async def test_valid_session(
        self,
        test_config: Config,
        dashboard_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test valid session returns logged_in=True."""
        cookies = SessionCookies(phpsessid="session123", il_client_id="client456")

        respx_mock.get("https://ilias.test.de/ilias.php?baseClass=ilDashboardGUI").mock(
            return_value=httpx.Response(200, text=dashboard_html)
        )

        result = await check_session_status(test_config, cookies)

        assert result.logged_in is True
        assert result.username == "max.muster"

    @pytest.mark.asyncio
    async def test_expired_session_redirect(
        self,
        test_config: Config,
        login_redirect_html: str,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test expired session (redirect to login)."""
        cookies = SessionCookies(phpsessid="session123", il_client_id="client456")

        respx_mock.get("https://ilias.test.de/ilias.php?baseClass=ilDashboardGUI").mock(
            return_value=httpx.Response(200, text=login_redirect_html)
        )

        result = await check_session_status(test_config, cookies)

        assert result.logged_in is False
        assert result.message == "Session expired"

    @pytest.mark.asyncio
    async def test_401_unauthorized(
        self,
        test_config: Config,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test 401 response means expired session."""
        cookies = SessionCookies(phpsessid="session123", il_client_id="client456")

        respx_mock.get("https://ilias.test.de/ilias.php?baseClass=ilDashboardGUI").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        result = await check_session_status(test_config, cookies)

        assert result.logged_in is False

    @pytest.mark.asyncio
    async def test_network_error(
        self,
        test_config: Config,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test network error raises NetworkError."""
        cookies = SessionCookies(phpsessid="session123", il_client_id="client456")

        respx_mock.get("https://ilias.test.de/ilias.php?baseClass=ilDashboardGUI").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(NetworkError):
            await check_session_status(test_config, cookies)


class TestBrowserFallback:
    """Tests for browser fallback login."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires Playwright browser installation")
    async def test_browser_not_available(
        self,
        test_config: Config,
    ) -> None:
        """Test browser fallback raises BrowserNotAvailableError when Playwright not installed."""
        # This test runs without Playwright installed in test env
        def totp_callback() -> str:
            return "123456"

        async with AuthClient(test_config) as client:
            with pytest.raises(BrowserNotAvailableError):
                await client.login("testuser", "password123", totp_callback, browser_fallback=True)