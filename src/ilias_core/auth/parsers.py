"""HTML-Parser für die Keycloak- und ILIAS-Seiten.

Ein Modul pro Seitentyp, gekapselt und ohne Seiteneffekte. Alle Funktionen
arbeiten auf einem HTML-String und geben strukturierte Daten zurück.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

KEYCLOAK_LOGIN_FORM_ID = "kc-form-login"
KEYCLOAK_TOTP_FORM_ID = "kc-otp-login-form"

ERROR_SELECTORS = (
    "#input-error",
    ".pf-c-form__helper-text.pf-m-error",
    ".pf-c-alert__title",
    ".alert-error",
    ".kc-feedback-text",
    ".pf-m-error",
)


@dataclass
class HtmlForm:
    """Ein geparstes HTML-Formular."""

    action: str
    method: str
    fields: dict[str, str] = field(default_factory=dict)


def _parse_form(form) -> HtmlForm:  # noqa: ANN001 - bs4-Element
    action = form.get("action", "") or ""
    method = (form.get("method", "post") or "post").lower()
    fields: dict[str, str] = {}
    for element in form.find_all("input"):
        name = element.get("name")
        if not name:
            continue
        input_type = (element.get("type") or "text").lower()
        if input_type in ("submit", "button", "image", "file", "reset"):
            continue
        fields[name] = element.get("value", "") or ""
    return HtmlForm(action=action, method=method, fields=fields)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_keycloak_login(html: str, base_url: str = "") -> HtmlForm | None:
    """Parst das Keycloak-Login-Formular inklusive aller hidden inputs."""

    form = _soup(html).find("form", id=KEYCLOAK_LOGIN_FORM_ID)
    if form is None:
        return None
    parsed = _parse_form(form)
    parsed.action = urljoin(base_url, parsed.action)
    return parsed


def parse_keycloak_totp(html: str, base_url: str = "") -> HtmlForm | None:
    """Parst das Keycloak-TOTP-Formular inklusive aller hidden inputs."""

    form = _soup(html).find("form", id=KEYCLOAK_TOTP_FORM_ID)
    if form is None:
        return None
    parsed = _parse_form(form)
    parsed.action = urljoin(base_url, parsed.action)
    return parsed


def extract_keycloak_error(html: str) -> str | None:
    """Liefert die Fehlermeldung eines erneut angezeigten Keycloak-Formulars."""

    soup = _soup(html)
    for selector in ERROR_SELECTORS:
        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            if text:
                return text
    return None


def is_keycloak_login(html: str) -> bool:
    return _soup(html).find("form", id=KEYCLOAK_LOGIN_FORM_ID) is not None


def is_keycloak_totp(html: str) -> bool:
    return _soup(html).find("form", id=KEYCLOAK_TOTP_FORM_ID) is not None


def is_ilias_login_page(html: str) -> bool:
    """Erkennt die ILIAS-Login-Seite (Hinweis auf abgelaufene Session)."""

    soup = _soup(html)
    if soup.find("form", id="login_form") is not None:
        return True
    if soup.find("form", attrs={"name": "login_form"}) is not None:
        return True
    for form in soup.find_all("form"):
        action = form.get("action", "") or ""
        if "login.php" in action:
            return True
    text = soup.get_text(" ", strip=True)
    return "Ohne HHN-Konto anmelden" in text
