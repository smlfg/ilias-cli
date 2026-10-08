"""Tests for auth module - form parsers and helpers."""

import pytest

from ilias_core.auth import (
    parse_login_form,
    parse_totp_form,
    is_login_error_page,
    is_totp_page,
    parse_dashboard_username,
    is_login_redirect,
    ParsedForm,
)
from ilias_core.errors import ParserError


class TestParseLoginForm:
    """Tests for Keycloak login form parser."""

    def test_parse_valid_login_form(self, login_html: str) -> None:
        """Test parsing valid Keycloak login form."""
        form = parse_login_form(login_html)

        assert isinstance(form, ParsedForm)
        assert "session_code=abc123" in form.action_url
        assert "execution=def456" in form.action_url
        assert "client_id=hhn_common_ilias" in form.action_url
        assert "tab_id=ghi789" in form.action_url
        assert form.fields["username"] == ""
        assert form.fields["password"] == ""
        assert form.fields["credentialId"] == "cred-123"
        assert form.fields["rememberMe"] == "true"

    def test_parse_login_form_missing_form_raises(self, unexpected_html: str) -> None:
        """Test missing login form raises ValueError."""
        with pytest.raises(ValueError, match="Keycloak login form.*not found"):
            parse_login_form(unexpected_html)

    def test_parse_login_form_missing_action_raises(self) -> None:
        """Test login form without action raises ValueError."""
        html = '<form id="kc-form-login" method="post"><input name="username"><input name="password" type="password"></form>'
        with pytest.raises(ValueError, match="Login form missing action URL"):
            parse_login_form(html)

    def test_parse_login_form_missing_username_raises(self) -> None:
        """Test login form without username field raises ValueError."""
        html = '<form id="kc-form-login" action="/login" method="post"><input name="password" type="password"></form>'
        with pytest.raises(ValueError, match="Login form missing username field"):
            parse_login_form(html)

    def test_parse_login_form_missing_password_raises(self) -> None:
        """Test login form without password field raises ValueError."""
        html = '<form id="kc-form-login" action="/login" method="post"><input name="username"></form>'
        with pytest.raises(ValueError, match="Login form missing password field"):
            parse_login_form(html)


class TestParseTOTPForm:
    """Tests for Keycloak TOTP form parser."""

    def test_parse_valid_totp_form(self, totp_html: str) -> None:
        """Test parsing valid Keycloak TOTP form."""
        form = parse_totp_form(totp_html)

        assert isinstance(form, ParsedForm)
        assert "session_code=abc123" in form.action_url
        assert form.fields["otp"] == ""
        assert form.fields["credentialId"] == "cred-123"

    def test_parse_totp_form_missing_raises(self, unexpected_html: str) -> None:
        """Test missing TOTP form raises ValueError."""
        with pytest.raises(ValueError, match="Keycloak TOTP form not found"):
            parse_totp_form(unexpected_html)

    def test_parse_totp_form_missing_otp_raises(self) -> None:
        """Test TOTP form without otp field raises ValueError."""
        html = '<form id="kc-otp-login-form" action="/totp" method="post"><input name="credentialId" value="x"></form>'
        with pytest.raises(ValueError, match="TOTP form missing otp field"):
            parse_totp_form(html)


class TestIsLoginErrorPage:
    """Tests for login error detection."""

    def test_detects_error_page(self, login_error_html: str) -> None:
        """Test detection of login error page."""
        assert is_login_error_page(login_error_html) is True

    def test_no_error_on_normal_login(self, login_html: str) -> None:
        """Test normal login page is not detected as error."""
        assert is_login_error_page(login_html) is False

    def test_no_error_on_totp_page(self, totp_html: str) -> None:
        """Test TOTP page is not detected as login error."""
        assert is_login_error_page(totp_html) is False


class TestIsTOTPPage:
    """Tests for TOTP page detection."""

    def test_detects_totp_page(self, totp_html: str) -> None:
        """Test detection of TOTP page."""
        assert is_totp_page(totp_html) is True

    def test_not_totp_on_login_page(self, login_html: str) -> None:
        """Test login page is not detected as TOTP."""
        assert is_totp_page(login_html) is False


class TestParseDashboardUsername:
    """Tests for dashboard username extraction."""

    def test_extracts_username(self, dashboard_html: str) -> None:
        """Test username extraction from dashboard."""
        username = parse_dashboard_username(dashboard_html)
        assert username == "max.muster"

    def test_returns_none_on_login_page(self, login_redirect_html: str) -> None:
        """Test returns None on login page."""
        username = parse_dashboard_username(login_redirect_html)
        assert username is None


class TestIsLoginRedirect:
    """Tests for login redirect detection."""

    def test_detects_login_url(self) -> None:
        """Test detection via URL."""
        assert is_login_redirect("", "https://ilias.test.de/login.php") is True
        assert is_login_redirect("", "https://ilias.test.de/openidconnect.php") is True

    def test_detects_login_form_in_html(self, login_redirect_html: str) -> None:
        """Test detection via HTML form."""
        assert is_login_redirect(login_redirect_html, "https://ilias.test.de/ilias.php") is True

    def test_not_redirect_on_dashboard(self, dashboard_html: str) -> None:
        """Test dashboard is not detected as login redirect."""
        assert is_login_redirect(dashboard_html, "https://ilias.test.de/ilias.php") is False