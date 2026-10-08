"""Parsing of Keycloak login / TOTP forms (isolated module per page type)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ilias_core.errors import ParseError

LOGIN_FORM_ID = "kc-form-login"
OTP_FORM_ID = "kc-otp-login-form"


@dataclass
class ParsedForm:
    action: str
    inputs: dict[str, str] = field(default_factory=dict)


def _parse_form_by_id(html: str, form_id: str, page_url: str = "") -> ParsedForm:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id=form_id)
    if form is None:
        raise ParseError(f"Keycloak form '{form_id}' not found")
    action = form.get("action", "")
    if not action:
        raise ParseError(f"Keycloak form '{form_id}' has no action URL")
    if page_url:
        action = urljoin(page_url, action)
    inputs: dict[str, str] = {}
    for tag in form.find_all("input"):
        name = tag.get("name")
        if not name:
            continue
        inputs[name] = tag.get("value", "") or ""
    return ParsedForm(action=action, inputs=inputs)


def parse_login_form(html: str, page_url: str = "") -> ParsedForm:
    """Parse Keycloak username/password form (id=kc-form-login).

    Expected fields: username, password, optional hidden credentialId etc.
    All hidden inputs are returned in .inputs and must be re-posted.
    """
    form = _parse_form_by_id(html, LOGIN_FORM_ID, page_url)
    if "username" not in form.inputs or "password" not in form.inputs:
        raise ParseError("Login form misses username/password fields")
    return form


def parse_otp_form(html: str, page_url: str = "") -> ParsedForm:
    """Parse Keycloak TOTP form (id=kc-otp-login-form). Expected field: otp."""
    form = _parse_form_by_id(html, OTP_FORM_ID, page_url)
    if "otp" not in form.inputs:
        raise ParseError("OTP form misses otp field")
    return form


def has_login_form(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("form", id=LOGIN_FORM_ID) is not None


def has_otp_form(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("form", id=OTP_FORM_ID) is not None


def detect_login_error(html: str) -> str | None:
    """Return Keycloak error message if the login page shows one, else None.

    Keycloak renders errors e.g. in <span class="kc-feedback-text"> or
    <div class="alert-error"> / #input-error variants.
    """
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        ("span", "kc-feedback-text"),
        ("div", "alert-error"),
        ("div", "kc-feedback-text"),
        ("span", "input-error"),
    ]
    for tag, cls in selectors:
        el = soup.find(tag, class_=cls)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    # generic: aria / role=alert near login form
    form = soup.find("form", id=LOGIN_FORM_ID)
    if form is not None:
        alert = soup.find(attrs={"role": "alert"})
        if alert and alert.get_text(strip=True):
            return alert.get_text(strip=True)
    return None


def detect_otp_error(html: str) -> str | None:
    """Same as detect_login_error but for the OTP page."""
    msg = detect_login_error(html)
    if msg:
        return msg
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id=OTP_FORM_ID)
    if form is not None:
        alert = soup.find(attrs={"role": "alert"})
        if alert and alert.get_text(strip=True):
            return alert.get_text(strip=True)
        err = soup.find(class_="error")
        if err and err.get_text(strip=True):
            return err.get_text(strip=True)
    return None


def looks_like_ilias_logged_in(html: str) -> bool:
    """Heuristic: dashboard HTML of a logged-in ILIAS session."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    # Dashboard markers (robust, not version-specific)
    if "dashboard" in text or "persönlicher bereich" in text or "personal desktop" in text:
        if soup.find("form", id=LOGIN_FORM_ID) is None:
            return True
    # logout link present => logged in
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").lower()
        if "logout" in href:
            return True
    return False


def looks_like_ilias_login(html: str) -> bool:
    """Heuristic: ILIAS shows its own login page/form (session expired)."""
    lower = html.lower()
    if "login.php" in lower and ("login" in lower or "anmelden" in lower):
        return True
    soup = BeautifulSoup(html, "html.parser")
    # generic login form with password field on an ILIAS page
    for form in soup.find_all("form"):
        names = {i.get("name", "").lower() for i in form.find_all("input")}
        if "password" in names or "username" in names:
            return True
    return False
