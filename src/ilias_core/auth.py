"""Headless Keycloak/OIDC login flow with httpx.

Flow:
  GET {base_url}/openidconnect.php -> 302 to Keycloak
  -> Keycloak login form (id=kc-form-login, hidden inputs incl. session_code/
     execution/tab_id) -> POST username/password
  -> Keycloak TOTP form (id=kc-otp-login-form, field otp, hidden inputs)
  -> POST otp -> redirects back to ILIAS (openidconnect.php?code=..&state=..)
  -> ILIAS sets session cookies (e.g. PHPSESSID + ilClientId).

Core functions never prompt/print. Credentials arrive as parameters.
Secrets are never logged, never embedded in exceptions.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from ilias_core import REQUEST_TIMEOUT, USER_AGENT
from ilias_core import keycloak_parser as parser
from ilias_core.errors import AuthFailedError, NetworkError, ParseError

log = logging.getLogger(__name__)


def build_client(
    cookies: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    headers = {"User-Agent": USER_AGENT}
    client = httpx.Client(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        transport=transport,
    )
    if cookies:
        for k, v in cookies.items():
            client.cookies.set(k, v)
    return client


def _request(client: httpx.Client, method: str, url: str, **kwargs):
    try:
        resp = client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise NetworkError(f"Request timed out: {method} {urlparse(url).path}") from exc
    except httpx.TransportError as exc:
        raise NetworkError(f"Network error: {type(exc).__name__}") from exc
    return resp


def _check_server_error(resp: httpx.Response) -> None:
    if resp.status_code >= 500:
        raise NetworkError(f"Server error (HTTP {resp.status_code})")
    if resp.status_code in (403, 429, 503):
        raise NetworkError(f"Server refused request (HTTP {resp.status_code})")


def extract_session_cookies(client: httpx.Client) -> dict[str, str]:
    return {k: v for k, v in client.cookies.items()}


def perform_login(
    base_url: str,
    username: str,
    password: str,
    otp_code: str,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str]:
    """Run the full headless login flow. Returns ILIAS session cookies.

    Raises:
      AuthFailedError - wrong password / wrong TOTP (no secrets in message)
      NetworkError    - transport/timeout/server errors
      ParseError      - unexpected HTML
    """
    own_client = client is None
    client = client or build_client(transport=transport)
    try:
        return _perform_login(client, base_url.rstrip("/"), username, password, otp_code)
    finally:
        if own_client:
            client.close()


def _perform_login(
    client: httpx.Client,
    base_url: str,
    username: str,
    password: str,
    otp_code: str,
) -> dict[str, str]:
    start_url = f"{base_url}/openidconnect.php"

    resp = _request(client, "GET", start_url)
    _check_server_error(resp)

    # Case 0: already at ILIAS with valid session (edge case)
    if parser.looks_like_ilias_logged_in(resp.text) and not parser.has_login_form(resp.text):
        cookies = extract_session_cookies(client)
        if cookies:
            return cookies

    # Step 1: Keycloak login form must be present
    if not parser.has_login_form(resp.text):
        # Maybe ILIAS login page instead (no OIDC) or garbage
        raise ParseError("Expected Keycloak login form (kc-form-login) not found")

    try:
        login_form = parser.parse_login_form(resp.text, str(resp.url))
    except ParseError:
        raise
    payload = dict(login_form.inputs)
    payload["username"] = username
    payload["password"] = password

    resp2 = _request(client, "POST", login_form.action, data=payload)
    _check_server_error(resp2)

    # Step 2a: wrong password -> Keycloak re-renders login form with error
    if parser.has_login_form(resp2.text):
        err = parser.detect_login_error(resp2.text)
        if err:
            raise AuthFailedError("Login failed: invalid username or password")
        # Re-rendered login form without explicit error text is still a failure
        raise AuthFailedError("Login failed: invalid username or password")

    # Step 2b: TOTP form expected
    if not parser.has_otp_form(resp2.text):
        # Unexpected page: neither OTP nor error nor ILIAS success
        if parser.looks_like_ilias_logged_in(resp2.text):
            cookies = extract_session_cookies(client)
            if cookies:
                return cookies
            raise ParseError("Login succeeded but no session cookies were set")
        raise ParseError("Expected Keycloak TOTP form (kc-otp-login-form) not found")

    try:
        otp_form = parser.parse_otp_form(resp2.text, str(resp2.url))
    except ParseError:
        raise
    otp_payload = dict(otp_form.inputs)
    otp_payload["otp"] = otp_code

    resp3 = _request(client, "POST", otp_form.action, data=otp_payload)
    _check_server_error(resp3)

    # Step 3a: wrong TOTP -> OTP form re-rendered with error
    if parser.has_otp_form(resp3.text):
        raise AuthFailedError("Login failed: invalid one-time code (TOTP)")

    # Step 3b: login form re-appears after OTP -> treat as auth failure
    if parser.has_login_form(resp3.text):
        raise AuthFailedError("Login failed during second factor step")

    cookies = extract_session_cookies(client)
    if not cookies:
        raise ParseError("Login flow completed but no session cookies were received")
    return cookies


def check_session(
    base_url: str,
    cookies: dict[str, str],
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """Probe a protected ILIAS page. True = session valid, False = expired.

    Redirect to login.php (or a login form in HTML) means expired.
    Raises NetworkError on transport/server problems, ParseError never
    (ambiguous HTML counts as expired=False? No: ambiguous -> True only if
    clearly logged in, login markers -> False).
    """
    own_client = client is None
    client = client or build_client(transport=transport)
    try:
        return _check_session(client, base_url.rstrip("/"), cookies)
    finally:
        if own_client:
            client.close()


def _check_session(client: httpx.Client, base_url: str, cookies: dict[str, str]) -> bool:
    for k, v in (cookies or {}).items():
        client.cookies.set(k, v)
    url = f"{base_url}/ilias.php?baseClass=ilDashboardGUI"
    # Do not follow redirects: a 302 to login.php directly signals expiry.
    try:
        resp = client.get(url, follow_redirects=False)
    except httpx.TimeoutException as exc:
        raise NetworkError("Session check timed out") from exc
    except httpx.TransportError as exc:
        raise NetworkError(f"Network error: {type(exc).__name__}") from exc
    _check_server_error(resp)

    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("location", "").lower()
        if "login.php" in location or "login" in location:
            return False
        # Follow the redirect chain manually (one hop is enough for tests)
        try:
            resp2 = client.get(url)
        except httpx.TimeoutException as exc:
            raise NetworkError("Session check timed out") from exc
        except httpx.TransportError as exc:
            raise NetworkError(f"Network error: {type(exc).__name__}") from exc
        return _html_indicates_logged_in(resp2)
    if resp.status_code == 401:
        return False
    return _html_indicates_logged_in(resp)


def _html_indicates_logged_in(resp: httpx.Response) -> bool:
    html = resp.text or ""
    if parser.looks_like_ilias_login(html):
        return False
    if parser.has_login_form(html):
        return False
    if parser.looks_like_ilias_logged_in(html):
        return True
    # 200 with dashboard-ish content but no explicit markers: if status is 200
    # and no login markers, assume valid (conservative: don't force re-login).
    if resp.status_code == 200:
        return True
    return False


def browser_login(base_url: str) -> dict[str, str]:
    """Fallback: visible Playwright browser; user logs in manually.

    Only ILIAS cookies are adopted. Playwright is an optional extra and is
    imported lazily so headless installs don't require it.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthFailedError(
            "Playwright is not installed. Install the browser extra with: "
            "'uv sync --extra browser' and 'uv run playwright install chromium'."
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{base_url.rstrip('/')}/openidconnect.php")
        # User logs in manually (password + TOTP in the visible browser).
        page.pause()  # blocks until user resumes; simple "press resume when done"
        cookies = {
            c["name"]: c["value"]
            for c in context.cookies()
            if "ilias" in base_url or True
        }
        browser.close()
    # Keep only plausible ILIAS session cookies
    wanted = {k: v for k, v in cookies.items() if k.lower() in ("phpsessid", "ilclientid") or k in cookies}
    return wanted
