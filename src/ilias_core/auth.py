"""Keycloak form parsers and authentication client for ILIAS login flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ilias_core.config import Config
from ilias_core.errors import (
    BrowserNotAvailableError,
    InvalidCredentialsError,
    InvalidTOTPError,
    NetworkError,
    ParserError,
)
from ilias_core.models import LoginResult, SessionCookies, SessionStatus


@dataclass
class ParsedForm:
    """Parsed form data."""

    action_url: str
    fields: dict[str, str]
    method: str = "POST"


def parse_login_form(html: str) -> ParsedForm:
    """
    Parse Keycloak login form (kc-form-login).

    Expected form:
    <form id="kc-form-login" action="https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate?session_code=...&execution=...&client_id=hhn_common_ilias&tab_id=..." method="post">
      <input name="username" ...>
      <input name="password" type="password" ...>
      <input name="credentialId" type="hidden" value="...">
      ...
    </form>
    """
    parser = HTMLParser(html)
    form = parser.css_first("#kc-form-login")

    if form is None:
        raise ValueError("Keycloak login form (kc-form-login) not found in HTML")

    action = form.attributes.get("action", "")
    if not action:
        raise ValueError("Login form missing action URL")

    fields = {}
    for input_tag in form.css("input"):
        name = input_tag.attributes.get("name")
        value = input_tag.attributes.get("value", "")
        input_type = input_tag.attributes.get("type", "")
        if name and input_type not in ("submit", "button", "image", "reset"):
            fields[name] = value

    # Ensure required fields exist
    if "username" not in fields:
        raise ValueError("Login form missing username field")
    if "password" not in fields:
        raise ValueError("Login form missing password field")

    return ParsedForm(action_url=action, fields=fields)


def parse_totp_form(html: str) -> ParsedForm:
    """
    Parse Keycloak TOTP form (kc-otp-login-form).

    Expected form:
    <form id="kc-otp-login-form" action=".../login-actions/authenticate?..." method="post">
      <input name="otp" ...>
      <input name="credentialId" type="hidden" value="...">
      ...
    </form>
    """
    parser = HTMLParser(html)
    form = parser.css_first("#kc-otp-login-form")

    if form is None:
        # Try alternative selector
        form = parser.css_first("form[id*='otp']")
        if form is None:
            form = parser.css_first("form[action*='authenticate']")
            if form is None:
                raise ValueError("Keycloak TOTP form not found in HTML")

    action = form.attributes.get("action", "")
    if not action:
        raise ValueError("TOTP form missing action URL")

    fields = {}
    for input_tag in form.css("input"):
        name = input_tag.attributes.get("name")
        value = input_tag.attributes.get("value", "")
        input_type = input_tag.attributes.get("type", "")
        if name and input_type not in ("submit", "button", "image", "reset"):
            fields[name] = value

    if "otp" not in fields:
        raise ValueError("TOTP form missing otp field")

    return ParsedForm(action_url=action, fields=fields)


def is_login_error_page(html: str) -> bool:
    """Check if the page shows a login error (invalid credentials)."""
    parser = HTMLParser(html)
    # Keycloak shows error in #kc-form-login with .alert-error or similar
    error_alert = parser.css_first(".alert-error, .kc-feedback-text, #kc-form-login .alert")
    if error_alert:
        text = error_alert.text(strip=True).lower()
        if any(keyword in text for keyword in ["invalid", "incorrect", "wrong", "failed", "fehler", "ungültig"]):
            return True
    return False


def is_totp_page(html: str) -> bool:
    """Check if the page is a TOTP challenge page."""
    parser = HTMLParser(html)
    return parser.css_first("#kc-otp-login-form") is not None


def parse_dashboard_username(html: str) -> str | None:
    """Extract username from ILIAS dashboard page if logged in."""
    parser = HTMLParser(html)
    # ILIAS shows username in various places, try common ones
    user_elem = parser.css_first(".il_HeaderUserMenuUsername, .il-header-username, #il_usr_name, .user-name")
    if user_elem:
        return user_elem.text(strip=True)
    return None


def is_login_redirect(html: str, url: str) -> bool:
    """Check if response is a redirect to login page."""
    if "login.php" in url or "openidconnect.php" in url:
        return True
    parser = HTMLParser(html)
    # Check for login form in ILIAS
    return parser.css_first("#login_form, form[action*='login.php']") is not None


class AuthClient:
    """HTTP client for ILIAS/Keycloak authentication flow."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AuthClient:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout),
            follow_redirects=True,
            headers={"User-Agent": self.config.user_agent},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("AuthClient not initialized. Use async context manager.")
        return self._client

    async def login(
        self,
        username: str,
        password: str,
        totp_callback: Callable[[], str],
        *,
        browser_fallback: bool = False,
    ) -> LoginResult:
        """
        Perform headless login flow.

        Args:
            username: HHN username
            password: HHN password (never logged)
            totp_callback: Callable that returns TOTP code when needed
            browser_fallback: If True, use browser-based login instead

        Returns:
            LoginResult with session cookies on success
        """
        if browser_fallback:
            return await self._login_browser(username, password, totp_callback)
        return await self._login_headless(username, password, totp_callback)

    async def _login_headless(
        self,
        username: str,
        password: str,
        totp_callback: Callable[[], str],
    ) -> LoginResult:
        """Headless login via Keycloak forms."""
        try:
            # Step 1: GET openidconnect.php -> redirects to Keycloak
            resp = await self.client.get(self.config.openidconnect_url)
            resp.raise_for_status()

            # Should now be at Keycloak login page
            html = resp.text

            # Step 2: Parse login form
            try:
                login_form = parse_login_form(html)
            except ValueError as e:
                raise ParserError(f"Failed to parse Keycloak login form: {e}") from e

            # Step 3: POST credentials
            login_form.fields["username"] = username
            login_form.fields["password"] = password

            resp = await self.client.post(
                login_form.action_url,
                data=login_form.fields,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            html = resp.text

            # Check for login error
            if is_login_error_page(html):
                raise InvalidCredentialsError("Invalid username or password")

            # Step 4: Check if TOTP required
            if is_totp_page(html):
                try:
                    totp_form = parse_totp_form(html)
                except ValueError as e:
                    raise ParserError(f"Failed to parse Keycloak TOTP form: {e}") from e

                totp_code = totp_callback()
                totp_form.fields["otp"] = totp_code

                resp = await self.client.post(
                    totp_form.action_url,
                    data=totp_form.fields,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                html = resp.text

                # Check for TOTP error
                if is_login_error_page(html) or is_totp_page(html):
                    raise InvalidTOTPError("Invalid TOTP code")

            # Step 5: Follow redirects back to ILIAS and extract cookies
            # The final response should have ILIAS session cookies
            cookies = self._extract_ilias_cookies(resp)

            if not cookies.phpsessid or not cookies.il_client_id:
                raise ParserError("Failed to obtain ILIAS session cookies after login")

            return LoginResult(
                success=True,
                message="Login successful",
                cookies=cookies,
            )

        except httpx.HTTPStatusError as e:
            raise NetworkError(f"HTTP error during login: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise NetworkError(f"Network error during login: {e}") from e
        except (InvalidCredentialsError, InvalidTOTPError, ParserError):
            raise
        except Exception as e:
            raise ParserError(f"Unexpected error during login: {e}") from e

    async def _login_browser(
        self,
        username: str,
        password: str,
        totp_callback: Callable[[], str],
    ) -> LoginResult:
        """Browser-based login fallback using Playwright."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise BrowserNotAvailableError(
                "Playwright not installed. Install with 'uv sync --extra browser' or 'pip install playwright'"
            ) from e

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Visible browser
            context = await browser.new_context(user_agent=self.config.user_agent)
            page = await context.new_page()

            try:
                # Navigate to openidconnect.php
                await page.goto(self.config.openidconnect_url, wait_until="networkidle")

                # Wait for Keycloak login form
                await page.wait_for_selector("#kc-form-login", timeout=30000)

                # Fill credentials
                await page.fill('input[name="username"]', username)
                await page.fill('input[name="password"]', password)
                await page.click('input[type="submit"], button[type="submit"]')

                # Wait for either TOTP or redirect
                try:
                    await page.wait_for_selector("#kc-otp-login-form", timeout=10000)
                    # TOTP required
                    totp_code = totp_callback()
                    await page.fill('input[name="otp"]', totp_code)
                    await page.click('input[type="submit"], button[type="submit"]')
                except Exception:
                    # No TOTP form, continue
                    pass

                # Wait for redirect back to ILIAS
                await page.wait_for_url(f"{self.config.base_url}**", timeout=30000)

                # Extract cookies
                cookies = await context.cookies()
                await browser.close()

                session_cookies = self._cookies_to_session(cookies)
                if not session_cookies.phpsessid or not session_cookies.il_client_id:
                    raise ParserError("Failed to obtain ILIAS session cookies from browser")

                return LoginResult(
                    success=True,
                    message="Login successful (browser)",
                    cookies=session_cookies,
                )

            except Exception as e:
                await browser.close()
                if isinstance(e, (InvalidCredentialsError, InvalidTOTPError, ParserError, NetworkError, BrowserNotAvailableError)):
                    raise
                raise ParserError(f"Browser login failed: {e}") from e

    def _extract_ilias_cookies(self, response: httpx.Response) -> SessionCookies:
        """Extract ILIAS session cookies from response."""
        cookies = {}
        for name, value in response.cookies.items():
            cookies[name] = value

        # Also check redirect history
        for resp in response.history:
            for name, value in resp.cookies.items():
                if name not in cookies:
                    cookies[name] = value

        # Also parse Set-Cookie header manually to catch multiple cookies
        # httpx only parses the first cookie from comma-separated Set-Cookie header
        set_cookie_header = response.headers.get("Set-Cookie", "")
        if set_cookie_header:
            for cookie_part in set_cookie_header.split(","):
                cookie_part = cookie_part.strip()
                if "=" in cookie_part:
                    name_value = cookie_part.split(";")[0].strip()
                    if "=" in name_value:
                        name, value = name_value.split("=", 1)
                        cookies[name.strip()] = value.strip()

        return SessionCookies.from_dict(cookies)

    def _cookies_to_session(self, cookies: list[dict]) -> SessionCookies:
        """Convert Playwright cookies to SessionCookies."""
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        return SessionCookies.from_dict(cookie_dict)


async def check_session_status(config: Config, cookies: SessionCookies) -> SessionStatus:
    """Check if session is still valid by accessing protected page."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout),
        follow_redirects=True,
        headers={
            "User-Agent": config.user_agent,
            "Cookie": cookies.get_cookie_header(),
        },
    ) as client:
        try:
            resp = await client.get(config.dashboard_url)
            resp.raise_for_status()

            html = resp.text
            final_url = str(resp.url)

            # Check if redirected to login
            if is_login_redirect(html, final_url):
                return SessionStatus(
                    logged_in=False,
                    message="Session expired",
                )

            # Try to extract username
            username = parse_dashboard_username(html)
            if username:
                return SessionStatus(
                    logged_in=True,
                    message="Session valid",
                    username=username,
                )

            # If we got here but no username, might still be logged in
            return SessionStatus(
                logged_in=True,
                message="Session valid (username not detected)",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return SessionStatus(logged_in=False, message="Session expired")
            raise NetworkError(f"HTTP error checking session: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise NetworkError(f"Network error checking session: {e}") from e
        except Exception as e:
            raise ParserError(f"Error parsing session status: {e}") from e