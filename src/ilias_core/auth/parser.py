"""Parser für Keycloak-Formulare (eigenes Modul, gekapselt).

Erwartete Struktur (Keycloak, HHN-Realm ``hhn``):

* Login:  ``<form id="kc-form-login" action=".../login-actions/authenticate?...">``
  mit Feldern ``username``, ``password`` und ggf. hidden ``credentialId``.
* TOTP:   ``<form id="kc-otp-login-form" action=".../login-actions/authenticate?...">``
  mit Feld ``otp`` und ggf. hidden Inputs.

Fehler werden über ``id="kc-error-message"``, ``class="alert-error"`` bzw.
``id="input-error"`` erkannt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ilias_core.errors import ParserError

LOGIN_FORM_ID = "kc-form-login"
TOTP_FORM_ID = "kc-otp-login-form"


@dataclass
class LoginForm:
    """Geparstes Keycloak-Login-Formular."""

    action: str
    hidden: dict[str, str] = field(default_factory=dict)


@dataclass
class TotpForm:
    """Geparstes Keycloak-TOTP-Formular."""

    action: str
    hidden: dict[str, str] = field(default_factory=dict)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _parse_form(html: str, form_id: str) -> tuple[str, dict[str, str]]:
    soup = _soup(html)
    form = soup.find("form", id=form_id)
    if form is None:
        raise ParserError(f"Formular '{form_id}' nicht im HTML gefunden")
    action = form.get("action")
    if not action:
        raise ParserError(f"Formular '{form_id}' hat kein action-Attribut")
    hidden: dict[str, str] = {}
    for inp in form.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        if name:
            hidden[name] = inp.get("value", "")
    return str(action), hidden


def parse_login_form(html: str) -> LoginForm:
    """Login-Formular parsen; ParserError wenn nicht gefunden."""
    action, hidden = _parse_form(html, LOGIN_FORM_ID)
    return LoginForm(action=action, hidden=hidden)


def parse_totp_form(html: str) -> TotpForm:
    """TOTP-Formular parsen; ParserError wenn nicht gefunden."""
    action, hidden = _parse_form(html, TOTP_FORM_ID)
    return TotpForm(action=action, hidden=hidden)


def _has_error(html: str) -> bool:
    soup = _soup(html)
    if soup.find(id="kc-error-message"):
        return True
    if soup.find(class_="alert-error"):
        return True
    if soup.find(id="input-error"):
        return True
    return False


def is_login_page(html: str) -> bool:
    """True wenn die Seite ein Login-Formular enthält (Keycloak oder ILIAS).

    Wird verwendet, um eine abgelaufene Session zu erkennen: ILIAS leitet
    auf ``login.php`` bzw. zurück zu Keycloak.
    """
    soup = _soup(html)
    if soup.find("form", id=LOGIN_FORM_ID):
        return True
    if soup.find("form", id=TOTP_FORM_ID):
        return True
    for form in soup.find_all("form"):
        action = form.get("action") or ""
        if "login.php" in action:
            return True
    return False


def has_login_error(html: str) -> bool:
    """True wenn Keycloak eine Login-Fehler-Meldung zeigt (falsches Passwort)."""
    return _has_error(html)


def has_totp_error(html: str) -> bool:
    """True wenn Keycloak eine TOTP-Fehler-Meldung zeigt (falscher Code)."""
    return _has_error(html)
