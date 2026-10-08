"""Headless-Login-Flow mit httpx (nachgebauter Browser-Flow, KEIN Device-Flow).

Ablauf:
    GET  {base_url}/openidconnect.php        -> 302 auf Keycloak-Auth-URL
    GET  Keycloak-Auth-URL                   -> 200 Login-Formular
    POST Login-Formular (username/password)  -> 302 auf TOTP-Seite
                                               bzw. 200 mit Fehlermeldung
    POST TOTP-Formular (otp)                 -> 302 zurück zu ILIAS
    Redirects folgen                         -> ILIAS setzt Session-Cookies

Passwort und TOTP werden als Parameter übergeben (nie gespeichert, nie
geloggt). ``client`` kann für Tests (MockTransport) injiziert werden.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ilias_core.auth.parser import (
    has_login_error,
    has_totp_error,
    parse_login_form,
    parse_totp_form,
)
from ilias_core.errors import AuthenticationError, NetworkError, ParserError
from ilias_core.http import create_client
from ilias_core.models import LoginResult


def extract_session_cookies(client: httpx.Client, base_url: str) -> dict[str, str]:
    """Cookies des ILIAS-Hosts aus dem Cookie-Jar extrahieren.

    Keycloak-Cookies (login.hs-heilbronn.de) werden ignoriert.
    """
    host = urlparse(base_url).hostname or ""
    cookies: dict[str, str] = {}
    for cookie in client.cookies.jar:
        domain = (cookie.domain or "").lstrip(".")
        if domain and host and (host == domain or host.endswith(f".{domain}")):
            cookies[cookie.name] = cookie.value
    return cookies


def login(
    base_url: str,
    username: str,
    password: str,
    totp_code: str,
    *,
    client: httpx.Client | None = None,
) -> LoginResult:
    """Kompletten Login-Flow durchführen und die Session-Cookies zurückgeben."""
    if client is None:
        client = create_client()

    try:
        resp = client.get(f"{base_url}/openidconnect.php")
        login_form = parse_login_form(resp.text)

        resp = client.post(
            login_form.action,
            data={
                **login_form.hidden,
                "username": username,
                "password": password,
            },
        )
        if has_login_error(resp.text):
            raise AuthenticationError("Invalid username or password")
        totp_form = parse_totp_form(resp.text)

        resp = client.post(
            totp_form.action,
            data={**totp_form.hidden, "otp": totp_code},
        )
        if has_totp_error(resp.text):
            raise AuthenticationError("Invalid TOTP code")

        cookies = extract_session_cookies(client, base_url)
        if not cookies:
            raise ParserError(
                "Login abgeschlossen, aber keine Session-Cookies erhalten"
            )
        return LoginResult(cookies=cookies, final_url=str(resp.url))
    except httpx.HTTPError as exc:
        raise NetworkError(f"Netzwerkfehler während des Logins: {exc}") from exc
