"""Orchestrierung: Login, Status und Logout.

Alle Kernfunktionen arbeiten ohne Prompts und ohne ``print``. Passwort und
TOTP werden als Parameter bzw. Callback übergeben. Die Cookies werden nur
im ``SessionStore`` abgelegt und nie zurückgegeben.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from . import browser as browser_module
from .auth import KeycloakLoginFlow, is_ilias_login_page
from .config import Config, load_config
from .errors import NetworkError, NotLoggedInError, SessionExpiredError
from .http import build_client
from .models import LoginResult, SessionStatus
from .session import SessionStore

OtpCallback = Callable[[], str]
STATUS_URL = "{base_url}/ilias.php?baseClass=ilDashboardGUI"


class IliasClient:
    """Fassade über Auth, Session und Konfiguration."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        session_store: SessionStore | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or load_config()
        self.store = session_store or SessionStore(self.config)
        self._http_client = http_client

    # -- Login -----------------------------------------------------------
    def login(
        self,
        username: str,
        password: str,
        otp_callback: OtpCallback | None = None,
    ) -> LoginResult:
        client = self._client()
        try:
            cookies = KeycloakLoginFlow(self.config.base_url, client).authenticate(
                username, password, otp_callback
            )
        finally:
            self._close_if_owned(client)

        self.store.save(cookies)
        return LoginResult(
            authenticated=True,
            base_url=self.config.base_url,
            client_id=self.config.client_id,
            method="oidc",
            message="Login erfolgreich. Session wurde gespeichert.",
        )

    def login_with_browser(self, *, timeout: int = browser_module.DEFAULT_TIMEOUT) -> LoginResult:
        cookies = browser_module.login_with_browser(self.config.base_url, timeout=timeout)
        self.store.save(cookies)
        return LoginResult(
            authenticated=True,
            base_url=self.config.base_url,
            client_id=self.config.client_id,
            method="browser",
            message="Login im Browser erfolgreich. Session wurde gespeichert.",
        )

    # -- Status ----------------------------------------------------------
    def status(self) -> SessionStatus:
        cookies = self.store.load()
        if not cookies:
            raise NotLoggedInError(
                "Nicht eingeloggt. Bitte zuerst `ilias login` ausführen."
            )

        client = self._client()
        try:
            self._check_session(client, cookies)
        finally:
            self._close_if_owned(client)

        return SessionStatus(
            authenticated=True,
            base_url=self.config.base_url,
            client_id=self.config.client_id,
            message="Session ist gültig.",
        )

    def _check_session(self, client: httpx.Client, cookies: dict[str, str]) -> None:
        host = (urlparse(self.config.base_url).hostname or "").lower()
        for name, value in cookies.items():
            client.cookies.set(name, value, domain=host)

        url = STATUS_URL.format(base_url=self.config.base_url)
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise NetworkError("Netzwerkfehler bei der Session-Prüfung.") from exc

        if response.status_code in (401, 403):
            raise SessionExpiredError(
                "Session abgelaufen. Bitte erneut `ilias login` ausführen."
            )
        if response.status_code >= 400:
            raise NetworkError(f"Serverfehler (HTTP {response.status_code}).")

        final_path = urlparse(str(response.url)).path
        if final_path.endswith("login.php") or is_ilias_login_page(response.text):
            raise SessionExpiredError(
                "Session abgelaufen. Bitte erneut `ilias login` ausführen."
            )

    # -- Logout ----------------------------------------------------------
    def logout(self) -> bool:
        """Löscht die gespeicherte Session. Gibt zurück, ob eine existierte."""

        existed = self.store.load() is not None
        self.store.clear()
        return existed

    # -- Helfer ----------------------------------------------------------
    def _client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return build_client(self.config)

    def _close_if_owned(self, client: httpx.Client) -> None:
        if self._http_client is None:
            client.close()
