"""ILIAS-HTTP-Grundlage: Session laden, GET mit Status/Redirect-Prüfung, Request-Pause, Cookie-Rotation."""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import httpx

from .config import Config
from .errors import NetworkError, NotLoggedInError, SessionExpiredError
from .http import build_client
from .session import SessionStore

DEFAULT_REQUEST_INTERVAL = 1.0

ALLOWED_COOKIES = frozenset({"PHPSESSID", "ilClientId"})


def _get_request_interval() -> float:
    """Liest ILIAS_CLI_REQUEST_INTERVAL (Sekunden), Default 1.0."""
    val = os.environ.get("ILIAS_CLI_REQUEST_INTERVAL")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return DEFAULT_REQUEST_INTERVAL


class IliasHttpClient:
    """HTTP-Client für ILIAS-Anfragen mit Session-Handling und Prüfungen.

    Reihenfolge pro Antwort:
    1. Verbindungsfehler → exit 4 (NetworkError)
    2. HTTP >= 500 → exit 4 (NetworkError)
    3. Redirect auf login.php oder Login-Formular → exit 3 (SessionExpiredError)
    4. Dann erst parsen
    """

    def __init__(self, config: Config, session_store: SessionStore | None = None) -> None:
        self.config = config
        self.store = session_store or SessionStore(config)
        self._client: httpx.Client | None = None
        self._last_request_time: float = 0.0
        self._interval = _get_request_interval()

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = build_client(self.config, follow_redirects=True)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _respect_interval(self) -> None:
        if self._interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)

    def _load_session_cookies(self) -> dict[str, str]:
        cookies = self.store.load()
        if not cookies:
            raise NotLoggedInError(
                "Nicht eingeloggt. Bitte zuerst `ilias login` oder `ilias setup` ausführen.",
                hint=f"ilias login --instance {self.config.instance}",
            )
        host = (urlsplit(self.config.base_url).hostname or "").lower()
        for name, value in cookies.items():
            if name in ALLOWED_COOKIES:
                self.client.cookies.set(name, value, domain=host)
        return cookies

    def _save_session_cookies(self, cookies: dict[str, str]) -> None:
        allowed = {k: v for k, v in cookies.items() if k in ALLOWED_COOKIES}
        if allowed:
            self.store.save(allowed)

    def _check_response(self, response: httpx.Response, cookies_before: dict[str, str]) -> None:
        """Prüft Response auf Fehler gemäß Spec §7, §4.4."""
        # 1. Verbindungsfehler wird schon durch httpx geworfen
        # 2. HTTP >= 500
        if response.status_code >= 500:
            raise NetworkError(
                f"Serverfehler (HTTP {response.status_code}).",
                hint=f"Erreichbarkeit von {self.config.base_url} prüfen (ggf. VPN).",
            )

        # 3. Redirect auf login.php oder Login-Formular
        if response.url.path.endswith("login.php") or "cmd=force_login" in str(response.url):
            raise SessionExpiredError(
                "Session abgelaufen. Bitte erneut `ilias login` oder `ilias setup` ausführen.",
                hint=f"ilias login --instance {self.config.instance} oder ilias setup --instance {self.config.instance}",
            )

        # Check for login form in HTML
        html = response.text
        if self._is_login_page(html):
            raise SessionExpiredError(
                "Session abgelaufen. Bitte erneut `ilias login` oder `ilias setup` ausführen.",
                hint=f"ilias login --instance {self.config.instance} oder ilias setup --instance {self.config.instance}",
            )

        # 4. Check for rotated PHPSESSID and save
        self._save_session_cookies(dict(response.cookies))

    @staticmethod
    def _is_login_page(html: str) -> bool:
        """Erkennt ILIAS-Login-Seite (vereinfachte Prüfung)."""
        return "login.php" in html or "cmd=force_login" in html or "Ohne HHN-Konto anmelden" in html

    def get(self, path: str, *, label: str = "Anfrage") -> httpx.Response:
        """Führt GET-Request mit allen Prüfungen aus."""
        self._respect_interval()
        self._last_request_time = time.monotonic()

        cookies_before = self._load_session_cookies()

        try:
            response = self.client.get(self.config.base_url + path)
        except httpx.RequestError as exc:
            raise NetworkError(
                f"{label} fehlgeschlagen: {type(exc).__name__} ({exc}).",
                hint=f"Erreichbarkeit von {self.config.base_url} prüfen (ggf. VPN).",
            ) from None

        self._check_response(response, cookies_before)
        return response

    def get_dashboard(self) -> httpx.Response:
        """Lädt das Dashboard zur Session-Prüfung."""
        return self.get("/ilias.php?baseClass=ilDashboardGUI", label="Dashboard-Prüfung")

    def get_memberships(self) -> httpx.Response:
        """Lädt 'Meine Kurse und Gruppen'."""
        return self.get("/ilias.php?baseClass=ilmembershipoverviewgui", label="Meine Kurse und Gruppen")