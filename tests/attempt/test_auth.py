from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from ilias_core import auth
from ilias_core.errors import AuthError, NetworkError, ParserError

BASE = "https://ilias.hs-heilbronn.de"
KC = "https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth"
AUTH_URL = "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"


def _fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


def _register_success_routes(router: respx.MockRouter) -> None:
    f = _fixtures()
    router.get(f"{BASE}/openidconnect.php").mock(
        side_effect=lambda request: (
            httpx.Response(302, headers={"location": f"{KC}?client_id=hhn_common_ilias&tab_id=t1"})
            if "code" not in request.url.params
            else httpx.Response(
                302,
                headers=[
                    ("location", f"{BASE}/ilias.php?baseClass=ilDashboardGUI"),
                    ("set-cookie", "PHPSESSID=testsession; path=/"),
                    ("set-cookie", "ilClientId=iliashhn; path=/"),
                ],
            )
        )
    )
    router.get(f"{KC}?client_id=hhn_common_ilias&tab_id=t1").mock(
        return_value=httpx.Response(200, text=(f / "keycloak_login.html").read_text())
    )
    router.post(url__startswith=AUTH_URL).mock(
        side_effect=[
            httpx.Response(200, text=(f / "keycloak_totp.html").read_text()),
            httpx.Response(
                302,
                headers={"location": f"{BASE}/openidconnect.php?code=xyz&state=abc"},
            ),
        ]
    )
    router.get(f"{BASE}/ilias.php?baseClass=ilDashboardGUI").mock(
        return_value=httpx.Response(200, text=(f / "ilias_dashboard.html").read_text())
    )


@respx.mock
def test_login_success() -> None:
    _register_success_routes(respx.mock)
    result = auth.login(BASE, "student", "geheim", lambda: "123456")
    assert "PHPSESSID" in result.cookies
    assert result.cookies.get("ilClientId") == "iliashhn"

    calls = respx.mock.calls
    posts = [c for c in calls if c.request.method == "POST"]
    assert len(posts) == 2
    body = posts[0].request.content.decode()
    assert "username=student" in body
    assert "password=geheim" in body
    assert "client_id=hhn_common_ilias" in body
    assert "session_code" in str(posts[0].request.url)
    body2 = posts[1].request.content.decode()
    assert "otp=123456" in body2


@respx.mock
def test_login_wrong_password() -> None:
    f = _fixtures()
    router = respx.mock
    router.get(f"{BASE}/openidconnect.php").mock(
        return_value=httpx.Response(302, headers={"location": f"{KC}?client_id=x"})
    )
    router.get(f"{KC}?client_id=x").mock(return_value=httpx.Response(200, text=(f / "keycloak_login.html").read_text()))
    router.post(url__startswith=AUTH_URL).mock(
        return_value=httpx.Response(200, text=(f / "keycloak_login_error.html").read_text())
    )
    with pytest.raises(AuthError):
        auth.login(BASE, "student", "falsch", lambda: "123456")


@respx.mock
def test_login_wrong_totp() -> None:
    f = _fixtures()
    router = respx.mock
    router.get(f"{BASE}/openidconnect.php").mock(
        return_value=httpx.Response(302, headers={"location": f"{KC}?client_id=x"})
    )
    router.get(f"{KC}?client_id=x").mock(return_value=httpx.Response(200, text=(f / "keycloak_login.html").read_text()))
    router.post(url__startswith=AUTH_URL).mock(
        side_effect=[
            httpx.Response(200, text=(f / "keycloak_totp.html").read_text()),
            httpx.Response(200, text=(f / "keycloak_totp_error.html").read_text()),
        ]
    )
    with pytest.raises(AuthError):
        auth.login(BASE, "student", "geheim", lambda: "000000")


@respx.mock
def test_login_unexpected_html() -> None:
    f = _fixtures()
    router = respx.mock
    router.get(f"{BASE}/openidconnect.php").mock(
        return_value=httpx.Response(302, headers={"location": f"{KC}?client_id=x"})
    )
    router.get(f"{KC}?client_id=x").mock(return_value=httpx.Response(200, text=(f / "unexpected.html").read_text()))
    with pytest.raises(ParserError) as ei:
        auth.login(BASE, "s", "p", lambda: "1")
    assert ei.value.exit_code == 5


@respx.mock
def test_login_network_error() -> None:
    respx.mock.get(f"{BASE}/openidconnect.php").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(NetworkError) as ei:
        auth.login(BASE, "s", "p", lambda: "1")
    assert ei.value.exit_code == 4
