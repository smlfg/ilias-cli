"""Tests für die Keycloak-Formular-Parser."""

from __future__ import annotations

import pytest

from ilias_core.auth.parser import (
    has_login_error,
    has_totp_error,
    parse_login_form,
    parse_totp_form,
)
from ilias_core.errors import ParserError


def test_parse_login_form(html):
    form = parse_login_form(html["login"])
    assert form.action.startswith(
        "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
    )
    assert "session_code" in form.action
    assert "execution" in form.action
    assert "tab_id" in form.action
    assert form.hidden["credentialId"] == ""


def test_parse_totp_form(html):
    form = parse_totp_form(html["totp"])
    assert form.action.startswith(
        "https://login.hs-heilbronn.de/realms/hhn/login-actions/authenticate"
    )
    assert form.hidden["session_code"] == "SESSIONCODE123"


def test_parse_login_form_not_found(html):
    with pytest.raises(ParserError):
        parse_login_form(html["totp"])


def test_parse_totp_form_not_found(html):
    with pytest.raises(ParserError):
        parse_totp_form(html["login"])


def test_has_login_error(html):
    assert has_login_error(html["login_error"]) is True
    assert has_login_error(html["login"]) is False


def test_has_totp_error(html):
    assert has_totp_error(html["totp_error"]) is True
    assert has_totp_error(html["totp"]) is False
