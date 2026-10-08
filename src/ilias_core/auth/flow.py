"""Headless-Login-Flow gegen ILIAS + Keycloak.

Der Ablauf bildet den normalen Browser-Flow nach:

1. ``GET {base_url}/openidconnect.php`` (302 zum Keycloak-Login)
2. Keycloak-Login-Formular parsen (action-URL + alle hidden inputs)
3. ``POST username/password``
4. Falls nötig: Keycloak-TOTP-Formular parsen und ``POST otp``
5. Redirects zurück zu ILIAS folgen, Session-Cookies einsammeln

Es werden ausschließlich die Cookies der ILIAS-Domain übernommen.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from ..errors import AuthenticationError, NetworkError, ParserError
from . import parsers

OtpCallback = Callable[[], str]

SESSION_COOKIE_NAME = "PHPSESSID"


class KeycloakLoginFlow:
    """Führt den OIDC-Login in einem ``httpx.Client`` aus."""

    def __init__(self, base_url: str, client: httpx.Client) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client

    # -- öffentliche API -------------------------------------------------
    def authenticate(
        self,
        username: str,
        password: str,
        otp_callback: OtpCallback | None = None,
    ) -> dict[str, str]:
        response = self._get(f"{self.base_url}/openidconnect.php")
        login_form = parsers.parse_keycloak_login(response.text, str(response.url))

        if login_form is None:
            cookies = self._ilias_cookies()
            if self._has_session(cookies):
                return cookies
            raise ParserError(
                "Keycloak-Login-Formular konnte nicht geparst werden "
                "(unerwartetes HTML)."
            )

        response = self._submit_credentials(login_form, username, password)
        response = self._complete_totp_if_required(response, otp_callback)

        html = response.text
        cookies = self._ilias_cookies()
        if not self._has_session(cookies):
            if parsers.is_keycloak_login(html) or parsers.is_keycloak_totp(html):
                message = parsers.extract_keycloak_error(html)
                raise AuthenticationError(message or "Anmeldung fehlgeschlagen.")
            raise ParserError(
                "Keine ILIAS-Session-Cookies nach dem Login gefunden "
                "(unerwartetes HTML)."
            )
        return cookies

    # -- interne Schritte ------------------------------------------------
    def _submit_credentials(
        self, form: parsers.HtmlForm, username: str, password: str
    ) -> httpx.Response:
        data = dict(form.fields)
        data["username"] = username
        data["password"] = password
        return self._post(form.action, data)

    def _complete_totp_if_required(
        self,
        response: httpx.Response,
        otp_callback: OtpCallback | None,
    ) -> httpx.Response:
        html = response.text

        if parsers.is_keycloak_login(html):
            message = parsers.extract_keycloak_error(html)
            raise AuthenticationError(message or "Benutzername oder Passwort ist falsch.")

        totp_form = parsers.parse_keycloak_totp(html, str(response.url))
        if totp_form is None:
            return response

        if otp_callback is None:
            raise AuthenticationError("TOTP-Code erforderlich.")
        otp = otp_callback() or ""
        if not otp.strip():
            raise AuthenticationError("Kein TOTP-Code eingegeben.")

        data = dict(totp_form.fields)
        data["otp"] = otp
        response = self._post(totp_form.action, data)

        if parsers.is_keycloak_totp(response.text) or parsers.is_keycloak_login(
            response.text
        ):
            message = parsers.extract_keycloak_error(response.text)
            raise AuthenticationError(message or "TOTP-Code ist ungültig.")
        return response

    # -- HTTP-Helfer -----------------------------------------------------
    def _get(self, url: str) -> httpx.Response:
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise NetworkError("Netzwerkfehler beim Login.") from exc
        self._ensure_no_server_error(response)
        return response

    def _post(self, url: str, data: dict[str, str]) -> httpx.Response:
        try:
            response = self.client.post(url, data=data)
        except httpx.HTTPError as exc:
            raise NetworkError("Netzwerkfehler während des Logins.") from exc
        self._ensure_no_server_error(response)
        return response

    @staticmethod
    def _ensure_no_server_error(response: httpx.Response) -> None:
        if response.status_code >= 500:
            raise NetworkError(f"Serverfehler (HTTP {response.status_code}).")

    def _ilias_cookies(self) -> dict[str, str]:
        host = (urlparse(self.base_url).hostname or "").lower()
        cookies: dict[str, str] = {}
        for cookie in self.client.cookies.jar:
            domain = (cookie.domain or "").lstrip(".").lower()
            if not domain or not cookie.name:
                continue
            if host == domain or host.endswith("." + domain):
                cookies[cookie.name] = cookie.value
        return cookies

    @staticmethod
    def _has_session(cookies: dict[str, str]) -> bool:
        return SESSION_COOKIE_NAME in cookies
