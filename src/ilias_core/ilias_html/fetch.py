"""Lesender ILIAS-HTTP-Zugriff (Spec §4.3, §7, §13.7): Session + geprüfter GET.

Regeln, die Reihenfolge ist verbindlich:

1. Gespeicherte Session laden; keine Session → 2 ``not_logged_in``.
2. Pro Antwort: Verbindungsfehler → 4 ``network_error``; HTTP ≥ 500 → 4.
3. Redirect-Kette endet auf ``login.php``/``cmd=force_login``/``reloadpublic=1``,
   Login-Formular oder Metabar mit ``login.php``- statt ``logout.php``-Link →
   3 ``session_expired`` (kein Auto-Re-Login, nie Keycloak kontaktieren).
4. ``.alert-danger`` im Hauptinhalt oder Redirect auf die Repository-Wurzel /
   eine andere ref_id als angefragt → 1 ``permission_denied`` (nicht parsen,
   nicht crawlen).
5. Erst dann parsen; fehlt die erwartete Struktur → 5 ``parse_error``
   (Seitentyp und URL ohne Query-Werte nennen).
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urlsplit

import httpx

from ..auth.parsers import is_ilias_login_page
from ..config import Config
from ..errors import (
    NetworkError,
    NotLoggedInError,
    PermissionDeniedError,
    SessionExpiredError,
)
from ..http import build_client, user_agent
from ..session import SessionStore

COOKIE_ALLOWLIST = frozenset({"PHPSESSID", "ilClientId"})
DEFAULT_REQUEST_INTERVAL = 1.0
ENV_REQUEST_INTERVAL = "ILIAS_CLI_REQUEST_INTERVAL"


def request_interval() -> float:
    raw = os.environ.get(ENV_REQUEST_INTERVAL)
    if raw is None:
        return DEFAULT_REQUEST_INTERVAL
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_REQUEST_INTERVAL
    return max(value, 0.0)


class IliasFetcher:
    """Nur-lesen-Session für ein Instanz-Profil; GET mit voller Fehlerprüfung."""

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

    def get(self, path: str, *, label: str = "Anfrage") -> httpx.Response:
        cookies = self.store.load()
        if not cookies:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.key}.",
                hint=f"Erst `ilias login --instance {self.key}` oder `ilias setup --instance {self.key}` ausführen.",
            )

        client = self._client if self._client is not None else build_client(
            self.config, follow_redirects=True
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
            raise NetworkError(f"{label}: Serverfehler HTTP {response.status_code} von {self.base_url}.")
        if self._is_login_chain(response) or is_ilias_login_page(response.text) or self._login_metabar(response.text):
            raise SessionExpiredError(
                f"{label}: ILIAS verlangt eine neue Anmeldung (Session abgelaufen).",
                hint=f"Erneut mit `ilias login --instance {self.key}` oder `ilias setup --instance {self.key}` anmelden (kein automatischer Re-Login).",
            )
        if self._is_forbidden(response):
            raise PermissionDeniedError(
                f"{label}: keine Berechtigung für das angefragte Objekt.",
                hint=f"`ilias courses --instance {self.key}` zeigt die vorhandenen Mitgliedschaften.",
            )
        return response

    @staticmethod
    def _is_login_chain(response: httpx.Response) -> bool:
        urls = [str(response.url)] + [str(r.headers.get("location", "")) for r in response.history]
        for candidate in urls:
            low = candidate.lower()
            if "login.php" in low or "cmd=force_login" in low or "reloadpublic=1" in low:
                return True
        return False

    @staticmethod
    def _login_metabar(html: str) -> bool:
        """Metabar mit login.php-Link statt Abmelden -> Session weg (Exit 3)."""
        m = re.search(r"<ul[^>]*il-maincontrols-metabar[^>]*>.*?</ul>", html, re.S)
        if not m:
            return False
        block = m.group(0).lower()
        return "login.php" in block and "logout.php" not in block

    @staticmethod
    def _is_forbidden(response: httpx.Response) -> bool:
        text = response.text
        m = re.search(r"#ilContentContainer.*", text, re.S)
        main = m.group(0) if m else text
        if 'class="alert alert-danger"' in main or "class='alert alert-danger'" in main:
            return True
        return False

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
            for name, value in client.cookies.items()
            if name in COOKIE_ALLOWLIST
        }
        if current and current != previous:
            self.store.save(current)

    def get_text(self, path: str, *, label: str = "Anfrage") -> str:
        return self.get(path, label=label).text
