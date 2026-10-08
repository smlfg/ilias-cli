"""Parser für Shibboleth/SAML und ILIAS, geprüft an den echten Uni-Mannheim-Seiten."""

from __future__ import annotations

from pathlib import Path

from ilias_core.auth import (
    is_ilias_logged_in,
    is_ilias_login_page,
    parse_saml_post,
    parse_shibboleth_consent,
    parse_shibboleth_login,
)
from ilias_core.auth.parsers import extract_shibboleth_error, parse_shibboleth_storage
from ilias_core.debuglog import redact_url

from helpers import fixture

REAL = Path(__file__).resolve().parent.parent / "fixtures" / "uni-mannheim"
IDP_URL = "https://idp.uni-mannheim.de/idp/profile/SAML2/Redirect/SSO?execution=e1s1"


def real(name: str) -> str:
    return (REAL / name).read_text(encoding="utf-8")


def test_real_idp_login_form():
    form = parse_shibboleth_login(real("idp_login.html"), IDP_URL)
    assert form is not None
    assert form.form_id == "login-form"
    assert form.action == IDP_URL
    assert form.method == "post"
    # Nur was ein Browser ohne Klick senden würde: hidden csrf_token, keine
    # nicht angehakten Checkboxen (donotcache, _shib_idp_revokeConsent).
    assert form.fields == {"csrf_token": "REDACTED", "j_username": "", "j_password": ""}
    assert "_eventId_proceed" in form.submit_names
    assert {"j_username", "j_password", "donotcache", "_shib_idp_revokeConsent"} <= set(form.field_names)


def test_real_idp_login_is_not_consent_or_saml():
    html = real("idp_login.html")
    assert parse_shibboleth_consent(html, IDP_URL) is None
    assert parse_saml_post(html, IDP_URL) is None
    assert parse_shibboleth_storage(html, IDP_URL) is None
    assert extract_shibboleth_error(html) is None


def test_real_ilias_login_page_detected():
    html = real("ilias_login.html")
    assert is_ilias_login_page(html)
    assert not is_ilias_logged_in(html)


def test_dashboard_marker():
    assert is_ilias_logged_in(fixture("ilias_dashboard.html"))
    assert not is_ilias_login_page(fixture("ilias_dashboard.html"))
    assert not is_ilias_logged_in("<html><body><h1>Dashboard</h1></body></html>")


def test_saml_post_form_with_entity_encoded_action():
    html = """<html><body onload="document.forms[0].submit()"><form
      action="https&#x3a;&#x2f;&#x2f;ilias.example.invalid&#x2f;Services&#x2f;Saml&#x2f;acs.php" method="post">
      <input type="hidden" name="RelayState" value="https&#x3a;&#x2f;&#x2f;ilias.example.invalid&#x2f;saml.php"/>
      <input type="hidden" name="SAMLResponse" value="PHNhbWw&#x2b;&#x3d;"/>
      <noscript><input type="submit" value="Continue"/></noscript></form></body></html>"""
    form = parse_saml_post(html, IDP_URL)
    assert form is not None
    assert form.action == "https://ilias.example.invalid/Services/Saml/acs.php"
    assert form.fields == {
        "RelayState": "https://ilias.example.invalid/saml.php",
        "SAMLResponse": "PHNhbWw+=",
    }


def test_consent_keeps_default_option():
    html = """<form action="/idp/profile/SAML2/Redirect/SSO?execution=e1s2" method="post">
      <input type="hidden" name="csrf_token" value="t"/>
      <input type="radio" name="_shib_idp_consentOptions" value="_shib_idp_doNotRememberConsent">
      <input type="radio" name="_shib_idp_consentOptions" value="_shib_idp_rememberConsent" checked>
      <input type="submit" name="_eventId_AttributeReleaseRejected" value="Ablehnen">
      <input type="submit" name="_eventId_proceed" value="Akzeptieren"></form>"""
    form = parse_shibboleth_consent(html, IDP_URL)
    assert form is not None
    assert form.fields == {"csrf_token": "t", "_shib_idp_consentOptions": "_shib_idp_rememberConsent"}
    assert form.action.endswith("execution=e1s2")


def test_shibboleth_error_message():
    html = real("idp_login.html").replace(
        '<div class="form-group login-username-section"',
        '<p class="form-element form-error">Das eingegebene Passwort ist falsch.</p><div class="form-group login-username-section"',
    )
    assert extract_shibboleth_error(html) == "Das eingegebene Passwort ist falsch."


def test_redact_url_keeps_only_routing_values():
    url = "https://ilias.example.invalid/openidconnect.php?code=SECRET&state=S2&baseClass=ilDashboardGUI&execution=e1s1#frag"
    redacted = redact_url(url)
    assert "SECRET" not in redacted and "S2" not in redacted and "frag" not in redacted
    assert redacted == (
        "https://ilias.example.invalid/openidconnect.php?code=…&state=…&baseClass=ilDashboardGUI&execution=e1s1"
    )
    assert "u:p" not in redact_url("https://u:p@host.example.invalid/x")
