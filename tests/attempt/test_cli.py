from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core import session
from ilias_core.models import SessionData

runner = CliRunner()
BASE = "https://ilias.hs-heilbronn.de"
KC = "https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth"
AUTH_URL = "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"


def _f() -> Path:
    return Path(__file__).parent / "fixtures"


def _mock_login_ok(router: respx.MockRouter) -> None:
    f = _f()
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
            httpx.Response(302, headers={"location": f"{BASE}/openidconnect.php?code=xyz&state=abc"}),
        ]
    )
    router.get(f"{BASE}/ilias.php?baseClass=ilDashboardGUI").mock(
        return_value=httpx.Response(200, text=(f / "ilias_dashboard.html").read_text())
    )


@respx.mock
def test_cli_login_success(caplog) -> None:
    _mock_login_ok(respx.mock)
    with caplog.at_level(logging.DEBUG):
        result = runner.invoke(app, ["login"], input="student\nGEHEIMPW\n123456\n")
    assert result.exit_code == 0, result.output
    assert "Eingeloggt" in result.output
    assert "GEHEIMPW" not in result.output
    assert "GEHEIMPW" not in caplog.text
    loaded = session.load_session()
    assert loaded is not None and "PHPSESSID" in loaded.cookies


def test_cli_status_not_logged_in() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2
    result_json = runner.invoke(app, ["status", "--json"])
    assert result_json.exit_code == 2
    data = json.loads(result_json.output)
    assert data["ok"] is False


@respx.mock
def test_cli_status_ok_and_json_has_no_cookies() -> None:
    session.save_session(SessionData(base_url=BASE, cookies={"PHPSESSID": "zzz", "ilClientId": "iliashhn"}))
    respx.mock.get(f"{BASE}/ilias.php?baseClass=ilDashboardGUI").mock(
        return_value=httpx.Response(200, text=(_f() / "ilias_dashboard.html").read_text())
    )
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["logged_in"] is True
    assert "PHPSESSID" not in result.output
    assert "zzz" not in result.output
    assert "ilClientId" not in result.output


@respx.mock
def test_cli_status_expired() -> None:
    session.save_session(SessionData(base_url=BASE, cookies={"PHPSESSID": "zzz"}))
    respx.mock.get(f"{BASE}/ilias.php?baseClass=ilDashboardGUI").mock(
        return_value=httpx.Response(302, headers={"location": f"{BASE}/login.php?target=x"})
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 3


@respx.mock
def test_cli_network_error_exit4() -> None:
    session.save_session(SessionData(base_url=BASE, cookies={"PHPSESSID": "zzz"}))
    respx.mock.get(f"{BASE}/ilias.php?baseClass=ilDashboardGUI").mock(side_effect=httpx.ConnectError("boom"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 4


def test_cli_logout() -> None:
    session.save_session(SessionData(base_url=BASE, cookies={"PHPSESSID": "zzz"}))
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert session.load_session() is None


def test_cli_help_commands() -> None:
    for args in (["--help"], ["login", "--help"], ["status", "--help"], ["logout", "--help"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, args
