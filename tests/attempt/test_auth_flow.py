"""Tests für den headless Login-Flow (httpx.MockTransport, kein Netzwerk)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from ilias_core.auth.flow import extract_session_cookies, login
from ilias_core.errors import (
    AuthenticationError,
    NetworkError,
    ParserError,
)

from conftest import (
    BASE_URL,
    KC_BASE,
    LOGIN_ACTION,
    TOTP_ACTION,
    VALID_OTP,
    VALID_PASSWORD,
    VALID_USERNAME,
)


def _posted_form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}


def test_successful_login_flow(success_client):
    client, requests = success_client
    result = login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)

    assert result.cookies.get("PHPSESSID") == "sessionabc123"
    assert result.cookies.get("ilClientId") == "iliashhn"
    assert result.final_url.startswith(BASE_URL)

    posts = [r for r in requests if r.method == "POST"]
    assert len(posts) == 2

    login_post, totp_post = posts
    assert login_post.url.path.endswith("/login-actions/authenticate")
    login_data = _posted_form(login_post)
    assert login_data["username"] == VALID_USERNAME
    assert login_data["password"] == VALID_PASSWORD
    assert login_data["credentialId"] == ""

    assert totp_post.url.path.endswith("/login-actions/authenticate")
    totp_data = _posted_form(totp_post)
    assert totp_data["otp"] == VALID_OTP
    assert totp_data["session_code"] == "SESSIONCODE123"


def test_login_follows_openidconnect_redirect(success_client):
    client, requests = success_client
    login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
    first = requests[0]
    assert first.method == "GET"
    assert first.url.path == "/openidconnect.php"


def test_wrong_password(success_client):
    client, _ = success_client
    with pytest.raises(AuthenticationError) as exc_info:
        login(BASE_URL, VALID_USERNAME, "wrongpass", VALID_OTP, client=client)
    assert exc_info.value.exit_code == 2
    assert "Invalid username or password" in str(exc_info.value)


def test_wrong_totp(success_client):
    client, _ = success_client
    with pytest.raises(AuthenticationError) as exc_info:
        login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, "000000", client=client)
    assert exc_info.value.exit_code == 2
    assert "Invalid TOTP code" in str(exc_info.value)


def test_unexpected_html_raises_parser_error(html):
    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/openidconnect.php":
            return httpx.Response(
                302,
                headers={"location": f"{KC_BASE}/realms/hhn/protocol/openid-connect/auth"},
            )
        if path.endswith("/protocol/openid-connect/auth"):
            return httpx.Response(200, html=html["login"])
        if path.endswith("/login-actions/authenticate"):
            if request.method == "GET":
                return httpx.Response(200, html=html["totp"])
            return httpx.Response(
                200, html="<html><body><h1>Unexpected Page</h1></body></html>"
            )
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    with pytest.raises(ParserError) as exc_info:
        login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
    assert exc_info.value.exit_code == 5


def test_network_error_raises_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    from ilias_core.errors import NetworkError as NE

    with pytest.raises(NE) as exc_info:
        login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
    assert exc_info.value.exit_code == 4


def test_extract_session_cookies_filters_keycloak(success_client):
    client, _ = success_client
    login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
    cookies = extract_session_cookies(client, BASE_URL)
    assert "PHPSESSID" in cookies
    assert "ilClientId" in cookies
    assert all("login" not in k for k in cookies)
