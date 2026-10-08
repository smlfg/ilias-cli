"""Kleine Lese-Grundlage für ILIAS-HTML-Seiten (S6, Spec §4.3/§7).

Bewusst unabhängig von der parallel entstehenden HTTP-Basis: nur ``GET``, die
gespeicherten Session-Cookies, eigener User-Agent und eine konfigurierbare
Pause (``ILIAS_CLI_REQUEST_INTERVAL``, Default 1.0 s). Vor jedem Parsen werden
in dieser Reihenfolge geprüft:

1. Verbindungsfehler -> Exit 4 (``NetworkError``)
2. HTTP >= 500 -> Exit 4
3. Redirect-Kette endet auf ``login.php``/``cmd=force_login``/``reloadpublic=1``,
   Login-Formular oder Metabar-Anmeldelink -> Exit 3 (``SessionExpiredError``,
   kein Re-Login, kein Keycloak-Kontakt)
4. ``.alert-danger`` im Hauptinhalt -> Exit 1 (``PermissionDeniedError``)
5. sonst wird geparst; ein leerer Rückgabewert bedeutet eine leere, gültige Seite.

Offline-Objekte sind kein Seitenfehler, nur ``visible: false`` (im Parser).
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from ..auth.parsers import is_ilias_login_page
from ..errors import (
    NetworkError,
    NotLoggedInError,
    PermissionDeniedError,
    SessionExpiredError,
)
from ..http import DEFAULT_TIMEOUT, user_agent
from ..session import SessionStore

REQUEST_INTERVAL_ENV = "ILIAS_CLI_REQUEST_INTERVAL"
DEFAULT_REQUEST_INTERVAL = 1.0
ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def request_interval() -> float:
    """Pause zwischen zwei Requests in Sekunden (Spec N2)."""

    raw = os.environ.get(REQUEST_INTERVAL_ENV)
    if raw is None:
        return DEFAULT_REQUEST_INTERVAL
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_REQUEST_INTERVAL


class IliasReadClient:
    """GET-Client auf der gespeicherten Session (Allowlist-Cookies aus dem Store)."""

    def __init__(self, instance, store: SessionStore | None = None) -> None:
        self.instance = instance
        self.base_url = instance.normalized_base_url
        self.store = store or SessionStore(instance)
        self._last_request: float | None = None

    def get(self, path: str, *, label: str = "Seite") -> httpx.Response:
        cookies = self.store.load()
        if not cookies:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` ausführen.",
            )

        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        self._pause()
        host = urlsplit(self.base_url).hostname or ""
        with httpx.Client(
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": user_agent(), "Accept": ACCEPT_HTML},
            trust_env=False,  # kein Proxy aus der Umgebung / keine echten Hosts im Test
        ) as client:
            for name, value in cookies.items():
                client.cookies.set(name, value, domain=host)
            try:
                response = client.get(url)
            except httpx.RequestError as exc:
                raise NetworkError(
                    f"{label}: Verbindung fehlgeschlagen ({type(exc).__name__}).",
                    hint=f"Erreichbarkeit von {self.base_url} prüfen (ggf. VPN).",
                ) from None
        self._last_request = time.monotonic()

        if response.status_code >= 500:
            raise NetworkError(f"{label}: Serverfehler HTTP {response.status_code}.")
        self._raise_if_login(response, label)
        self._raise_if_forbidden(response, label)
        return response

    # -- Checks ---------------------------------------------------------
    def _pause(self) -> None:
        interval = request_interval()
        if interval <= 0 or self._last_request is None:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < interval:
            time.sleep(interval - elapsed)

    def _raise_if_login(self, response: httpx.Response, label: str) -> None:
        for hop in (*response.history, response):
            parts = urlsplit(str(hop.url))
            query = parts.query.lower()
            path = parts.path.rstrip("/").lower()
            if path.endswith("login.php") or "cmd=force_login" in query or "reloadpublic=1" in query:
                raise self._expired(label)
        if is_ilias_login_page(response.text):
            raise self._expired(label)

    def _expired(self, label: str) -> SessionExpiredError:
        key = self.instance.key
        return SessionExpiredError(
            f"{label}: Session abgelaufen (ILIAS leitet zur Anmeldung um).",
            hint=(
                f"`ilias login --instance {key}` oder `ilias setup --instance {key}` "
                "ausführen (kein automatischer Re-Login)."
            ),
        )

    def _raise_if_forbidden(self, response: httpx.Response, label: str) -> None:
        soup = BeautifulSoup(response.text, "html.parser")
        scope = soup.select_one("#ilContentContainer") or soup
        if scope.select_one(".alert-danger") is not None:
            raise PermissionDeniedError(
                f"{label}: keine Berechtigung (ILIAS meldet einen Zugriffsfehler).",
                hint=(
                    f"Für diese Seite fehlt die Berechtigung; "
                    f"`ilias courses --instance {self.instance.key}` zeigt die zugänglichen Kurse."
                ),
            )
