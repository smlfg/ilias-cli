"""ILIAS-HTTP-Basis für lesende Befehle (`courses`, `ls`): Session + geprüfter GET.

Regeln (Spec §4, §7, L2/L3):

- Zuerst die gespeicherte Session laden. Keine Session -> Exit 2 (`not_logged_in`).
- Reihenfolge pro Antwort: Verbindungsfehler -> 4, HTTP >= 500 -> 4,
  Redirect auf ``login.php``/Login-Formular -> 3 (`session_expired`, Hinweis,
  **kein** Auto-Re-Login, kein Keycloak-Kontakt), dann erst parsen.
- Nur lesende ``GET``, eigener User-Agent, Pause über
  ``ILIAS_CLI_REQUEST_INTERVAL`` (Sekunden, Default 1.0).
- Rotiert ILIAS das ``PHPSESSID``, wird der neue Wert gespeichert – nur die
  Allowlist-Cookies (``PHPSESSID``, ``ilClientId``), nie Keycloak-Cookies.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import httpx

from .auth.parsers import is_ilias_login_page
from .auth.verify import ilias_cookies
from .config import Config
from .errors import NetworkError, NotLoggedInError, SessionExpiredError
from .http import build_client
from .session import SessionStore

#: L2: nur diese Cookies werden überhaupt gespeichert/weitergereicht.
COOKIE_ALLOWLIST = frozenset({"PHPSESSID", "ilClientId"})
DEFAULT_REQUEST_INTERVAL = 1.0
ENV_REQUEST_INTERVAL = "ILIAS_CLI_REQUEST_INTERVAL"


def request_interval() -> float:
    """Pause zwischen zwei Requests in Sekunden (Spec §4.3/N2)."""

    raw = os.environ.get(ENV_REQUEST_INTERVAL)
    if raw is None:
        return DEFAULT_REQUEST_INTERVAL
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_REQUEST_INTERVAL
    return max(value, 0.0)


class IliasWebSession:
    """Geprüfte, nur-lesende ILIAS-Session für ein Instanz-Profil."""

    def __init__(
        self,
        config: Config,
        *,
        session_store: SessionStore | None = None,
        client: httpx.Client | None = None,
        interval: float | None = None,
    ) -> None:
        self.config = config
        self.store = session_store or SessionStore(config)
        self._client = client
        self._interval = request_interval() if interval is None else max(interval, 0.0)
        self._last_request = 0.0

    @property
    def base_url(self) -> str:
        return self.config.normalized_base_url

    @property
    def key(self) -> str:
        return self.config.key

    def load_cookies(self) -> dict[str, str] | None:
        return self.store.load()

    def get(self, path: str, *, label: str = "Anfrage") -> httpx.Response:
        """``GET`` mit Session; wirft Exit-2/3/4-Fehler statt eines Tracebacks."""

        cookies = self.store.load()
        if not cookies:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.key}.",
                hint=f"Erst `ilias login --instance {self.key}` ausführen.",
            )

        client = self._client if self._client is not None else build_client(
            self.config, follow_redirects=False
        )
        owned = self._client is None
        try:
            host = (urlsplit(self.base_url).hostname or "").lower()
            for name, value in cookies.items():
                if name in COOKIE_ALLOWLIST:
                    client.cookies.set(name, value, domain=host)
            response = self._get_checked(client, path, label=label)
            self._store_rotated(client, cookies)
            return response
        finally:
            if owned:
                client.close()

    # -- intern ----------------------------------------------------------
    def _get_checked(self, client: httpx.Client, path: str, *, label: str) -> httpx.Response:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        self._throttle()
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise NetworkError(
                f"{label}: {self.base_url} ist nicht erreichbar ({type(exc).__name__}).",
                hint=f"Erreichbarkeit von {self.base_url} prüfen (ggf. VPN).",
            ) from None
        if response.status_code >= 500:
            raise NetworkError(
                f"{label}: Serverfehler HTTP {response.status_code} von {self.base_url}."
            )
        if self._is_login_redirect(response):
            raise self._session_expired(label)
        if is_ilias_login_page(response.text):
            raise self._session_expired(label)
        return response

    def _session_expired(self, label: str) -> SessionExpiredError:
        return SessionExpiredError(
            f"{label}: ILIAS verlangt eine neue Anmeldung (Session abgelaufen).",
            hint=(
                f"Erneut mit `ilias login --instance {self.key}` oder "
                f"`ilias setup --instance {self.key}` anmelden "
                "(kein automatischer Re-Login)."
            ),
        )

    @staticmethod
    def _is_login_redirect(response: httpx.Response) -> bool:
        if response.status_code not in (301, 302, 303, 307, 308):
            return False
        location = (response.headers.get("location") or "").lower()
        return "login.php" in location or "cmd=force_login" in location

    def _throttle(self) -> None:
        if self._interval <= 0:
            return
        now = time.monotonic()
        wait = self._interval - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _store_rotated(self, client: httpx.Client, previous: dict[str, str]) -> None:
        current = {
            name: value
            for name, value in ilias_cookies(client, self.base_url).items()
            if name in COOKIE_ALLOWLIST
        }
        if current and current != previous:
            self.store.save(current)
