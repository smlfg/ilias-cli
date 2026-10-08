"""Tests für die CLI-Befehle (typer.CliRunner, MockTransport, kein Netzwerk)."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core.models import LoginResult

from conftest import (
    BASE_URL,
    CLIENT_ID,
    VALID_OTP,
    VALID_PASSWORD,
    VALID_USERNAME,
    make_handler,
    save_session,
)

runner = CliRunner()


def _mock_client(html, handler_override=None):
    handler, _ = make_handler(html)
    if handler_override:
        handler = handler_override
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_help_commands():
    for args in (["--help"], ["login", "--help"], ["status", "--help"], ["logout", "--help"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output


def test_login_success(cli_env, html, monkeypatch):
    client = _mock_client(html)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)
    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME],
        input=f"{VALID_PASSWORD}\n{VALID_OTP}\n",
    )
    assert result.exit_code == 0, result.output
    assert cli_env.load() is not None


def test_login_json_output_has_no_cookies(cli_env, html, monkeypatch):
    client = _mock_client(html)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)
    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME, "--json"],
        input=f"{VALID_PASSWORD}\n{VALID_OTP}\n",
    )
    assert result.exit_code == 0, result.output
    json_line = result.output.strip().splitlines()[-1]
    payload = json.loads(json_line)
    assert payload["logged_in"] is True
    assert "cookies" not in payload
    assert VALID_PASSWORD not in result.output


def test_login_wrong_password_exit_2(cli_env, html, monkeypatch):
    client = _mock_client(html)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)
    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME],
        input=f"wrongpass\n{VALID_OTP}\n",
    )
    assert result.exit_code == 2
    assert cli_env.load() is None


def test_login_network_error_exit_4(cli_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)
    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME],
        input=f"{VALID_PASSWORD}\n{VALID_OTP}\n",
    )
    assert result.exit_code == 4


def test_login_unexpected_html_exit_5(cli_env, html, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import urlparse

        path = urlparse(str(request.url)).path
        if path == "/openidconnect.php":
            return httpx.Response(
                302,
                headers={"location": "https://login.example.com/realms/hhn/protocol/openid-connect/auth"},
            )
        if path.endswith("/protocol/openid-connect/auth"):
            return httpx.Response(200, html=html["login"])
        if path.endswith("/login-actions/authenticate"):
            if request.method == "GET":
                return httpx.Response(200, html=html["totp"])
            return httpx.Response(200, html="<html><body>Unexpected</body></html>")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)
    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME],
        input=f"{VALID_PASSWORD}\n{VALID_OTP}\n",
    )
    assert result.exit_code == 5


def test_login_browser_mocked(cli_env, monkeypatch):
    captured = {}

    def fake_browser_login(base_url):
        captured["base_url"] = base_url
        return LoginResult(cookies={"PHPSESSID": "browser123"}, final_url=f"{BASE_URL}/")

    monkeypatch.setattr(
        "ilias_cli.commands.login.login_with_browser", fake_browser_login
    )
    result = runner.invoke(app, ["login", "--browser"])
    assert result.exit_code == 0, result.output
    assert captured["base_url"] == BASE_URL
    assert cli_env.load().cookies["PHPSESSID"] == "browser123"


def test_status_logged_in_exit_0(cli_env, html, monkeypatch):
    save_session(cli_env, {"PHPSESSID": "abc", "ilClientId": CLIENT_ID})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html["dashboard"])

    client = _mock_client(html, handler)
    monkeypatch.setattr("ilias_core.session.manager.create_client", lambda: client)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "Eingeloggt" in result.output


def test_status_no_session_exit_2(cli_env):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2


def test_status_expired_exit_3(cli_env, html, monkeypatch):
    save_session(cli_env, {"PHPSESSID": "expired"})

    from urllib.parse import urlparse

    def handler(request: httpx.Request) -> httpx.Response:
        if urlparse(str(request.url)).path == "/login.php":
            return httpx.Response(200, html=html["login_page"])
        return httpx.Response(
            302, headers={"location": f"{BASE_URL}/login.php?client_id=iliashhn"}
        )

    client = _mock_client(html, handler)
    monkeypatch.setattr("ilias_core.session.manager.create_client", lambda: client)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 3
    assert "abgelaufen" in result.output.lower()


def test_status_json_output_has_no_cookies(cli_env, html, monkeypatch):
    save_session(cli_env, {"PHPSESSID": "abc", "ilClientId": CLIENT_ID})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html["dashboard"])

    client = _mock_client(html, handler)
    monkeypatch.setattr("ilias_core.session.manager.create_client", lambda: client)
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    json_line = result.output.strip().splitlines()[-1]
    payload = json.loads(json_line)
    assert payload["logged_in"] is True
    assert "cookies" not in payload
    assert "PHPSESSID" not in result.output


def test_logout_deletes_session(cli_env):
    save_session(cli_env, {"PHPSESSID": "abc"})
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0, result.output
    assert cli_env.load() is None


def test_logout_json(cli_env):
    save_session(cli_env, {"PHPSESSID": "abc"})
    result = runner.invoke(app, ["logout", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["logged_in"] is False


def test_logout_without_session_exit_2(cli_env):
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 2
