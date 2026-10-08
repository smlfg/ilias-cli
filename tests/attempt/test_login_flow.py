"""Tests für den kompletten Keycloak/OIDC-Login-Flow (ohne echtes Netzwerk)."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest
import respx

from ilias_core.client import IliasClient
from ilias_core.config import load_config
from ilias_core.errors import AuthenticationError, NetworkError, ParserError
from ilias_core.session import SessionStore

from helpers import (
    OPENIDC_URL,
    mock_successful_login,
    mock_unexpected_after_credentials,
    mock_wrong_password,
    mock_wrong_totp,
)


def _form(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode(), keep_blank_values=True)


def test_successful_login_with_totp(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=True) as router:
        routes = mock_successful_login(router)
        result = IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "123456")

    assert result.authenticated is True
    assert result.method == "oidc-keycloak"

    calls = routes["authenticate"].calls
    credentials = _form(calls[0].request.content)
    assert credentials["username"] == ["student"]
    assert credentials["password"] == ["geheim"]
    assert credentials["credentialId"] == [""]

    totp = _form(calls[1].request.content)
    assert totp["otp"] == ["123456"]
    assert totp["id"] == ["totp"]
    assert totp["credentialId"] == ["totp-credential"]

    cookies = SessionStore(cfg).load()
    assert cookies is not None
    assert cookies["PHPSESSID"] == "super-secret-session"
    assert cookies["ilClientId"] == "iliashhn"


def test_wrong_password_raises_authentication_error(config_dir, memory_keyring):
    cfg = load_config()
    otp_called = False

    def otp_callback() -> str:
        nonlocal otp_called
        otp_called = True
        return "123456"

    with respx.mock(assert_all_called=False) as router:
        mock_wrong_password(router)
        with pytest.raises(AuthenticationError) as excinfo:
            IliasClient(cfg).login("student", "falsch", otp_callback=otp_callback)

    assert "ungültig" in str(excinfo.value)
    assert otp_called is False
    assert SessionStore(cfg).load() is None


def test_wrong_totp_raises_authentication_error(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        mock_wrong_totp(router)
        with pytest.raises(AuthenticationError) as excinfo:
            IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "000000")

    assert "Authentifizierungscode" in str(excinfo.value)
    assert SessionStore(cfg).load() is None


def test_unexpected_html_raises_parser_error(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        router.get(OPENIDC_URL).mock(
            return_value=httpx.Response(200, text="<html><body>Wartung</body></html>")
        )
        with pytest.raises(ParserError):
            IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "123456")


def test_missing_cookies_after_login_raises_parser_error(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        mock_unexpected_after_credentials(router)
        with pytest.raises(ParserError):
            IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "123456")


def test_network_error_raises_network_error(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        router.get(OPENIDC_URL).mock(side_effect=httpx.ConnectError("kein Netz"))
        with pytest.raises(NetworkError):
            IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "123456")


def test_server_error_raises_network_error(config_dir, memory_keyring):
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        router.get(OPENIDC_URL).mock(return_value=httpx.Response(503, text="down"))
        with pytest.raises(NetworkError):
            IliasClient(cfg).login("student", "geheim", otp_callback=lambda: "123456")


def test_password_never_leaks(config_dir, memory_keyring, caplog, capsys):
    password = "SuperGeheimesPasswort-42"
    cfg = load_config()
    with respx.mock(assert_all_called=False) as router:
        mock_wrong_password(router)
        with pytest.raises(AuthenticationError) as excinfo:
            IliasClient(cfg).login("student", password, otp_callback=lambda: "123456")

    texts = [str(excinfo.value), repr(excinfo.value)]
    if excinfo.value.__cause__ is not None:
        texts.extend([str(excinfo.value.__cause__), repr(excinfo.value.__cause__)])
    assert all(password not in text for text in texts)

    captured = capsys.readouterr()
    assert password not in captured.out
    assert password not in captured.err
    assert password not in caplog.text

    stored = "".join(memory_keyring.store.values())
    assert password not in stored
