"""Tests für die HTML-Parser der Keycloak-/ILIAS-Seiten."""

from __future__ import annotations

from ilias_core.auth import (
    extract_keycloak_error,
    is_ilias_login_page,
    is_keycloak_login,
    is_keycloak_totp,
    parse_keycloak_login,
    parse_keycloak_totp,
)

from helpers import fixture


def test_parse_keycloak_login_form():
    form = parse_keycloak_login(fixture("keycloak_login.html"), "https://login.hs-heilbronn.de")
    assert form is not None
    assert form.method == "post"
    assert "login-actions/authenticate" in form.action
    assert "session_code=abc123session" in form.action
    assert form.fields["credentialId"] == ""
    # kein Submit-Button als Feld:
    assert "login" not in form.fields


def test_parse_keycloak_totp_form():
    form = parse_keycloak_totp(fixture("keycloak_totp.html"), "https://login.hs-heilbronn.de")
    assert form is not None
    assert "login-actions/authenticate" in form.action
    assert form.fields["id"] == "totp"
    assert form.fields["credentialId"] == "totp-credential"


def test_relative_action_is_resolved():
    html = '<html><form id="kc-form-login" action="/realms/hhn/auth" method="post"></form></html>'
    form = parse_keycloak_login(html, "https://login.hs-heilbronn.de/realms/x")
    assert form is not None
    assert form.action == "https://login.hs-heilbronn.de/realms/hhn/auth"


def test_extract_error_from_login_error_page():
    message = extract_keycloak_error(fixture("keycloak_login_error.html"))
    assert message is not None
    assert "ungültig" in message


def test_form_detection_flags():
    assert is_keycloak_login(fixture("keycloak_login.html"))
    assert not is_keycloak_totp(fixture("keycloak_login.html"))
    assert is_keycloak_totp(fixture("keycloak_totp.html"))
    assert not is_keycloak_login(fixture("keycloak_totp.html"))


def test_ilias_login_page_detection():
    assert is_ilias_login_page(fixture("ilias_login.php"))
    assert not is_ilias_login_page(fixture("ilias_dashboard.html"))


def test_unexpected_html_is_not_a_form():
    assert parse_keycloak_login("<html><body>Wartung</body></html>") is None
    assert parse_keycloak_totp("<html><body>Wartung</body></html>") is None
