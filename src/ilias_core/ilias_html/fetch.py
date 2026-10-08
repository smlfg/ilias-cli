"""Kleiner, rein lesender GET-Helfer für die ILIAS-HTML-Seiten.

Die **einzige** HTTP-Schicht für die lesenden ILIAS-Befehle (`courses`, `ls`): lädt die
gespeicherte Session (Cookies) aus dem vorhandenen ``SessionStore``, sendet nur GET mit
dem eigenen User-Agent, hält die Request-Pause ein und prüft **vor jedem Parsen** in
dieser Reihenfolge (Spec §7/§13.7):

1. Verbindungsfehler -> Exit 4,
2. HTTP >= 500 -> Exit 4,
3. Redirect auf ``login.php``/``cmd=force_login``/``reloadpublic=1``, in den Login-Fluss
   (``openidconnect``, Keycloak, Shibboleth/SAML) oder auf einen anderen Host als den
   ILIAS-Host (wird nie verfolgt), Login-Formular oder Metabar mit ``login.php`` statt
   ``logout.php`` -> Exit 3,
4. ``.alert-danger`` im Hauptinhalt bzw. Umleitung auf eine andere ref_id ->
   Exit 1 ``permission_denied``,
5. sonst URL/HTML an den Parser.

Rotiert ILIAS ``PHPSESSID``/``ilClientId`` (``Set-Cookie`` auf dem ILIAS-Host), wird der
neue Wert gespeichert (Spec §4.4, L2): nur Allowlist-Cookies, nie Keycloak-/Fremd-Cookies,
und nur nach einer Antwort, die keine abgelaufene Session meldet. Es gibt keinen
zusätzlichen Vorab-Request zur Session-Prüfung; die erste Seite eines Befehls ist die
Prüfung.

Zusätzlich: harte Obergrenze ``ILIAS_CLI_MAX_REQUESTS`` (Default 300) -> Exit 5
``crawl_limit`` ohne Teilausgabe. Offline-Objekte sind nur ``visible: false``,
kein Seitenfehler.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .. import debuglog
from ..auth.parsers import is_ilias_login_page
from ..auth.verify import ilias_cookies
from ..config import Config
from ..errors import (
    CrawlLimitError,
    NetworkError,
    NotLoggedInError,
    ParserError,
    PermissionDeniedError,
    SessionExpiredError,
)
from ..http import DEFAULT_TIMEOUT, user_agent
from ..session import SessionStore

DEFAULT_REQUEST_INTERVAL = 1.0
DEFAULT_MAX_REQUESTS = 300
MAX_REDIRECTS = 10
ALERT_DANGER_SELECTOR = ".alert-danger"
_LOGIN_MARKERS = ("login.php", "cmd=force_login", "reloadpublic=1")
#: Weiterleitungen in den Login-/IdP-Fluss (OIDC/Keycloak, SAML/Shibboleth). Ihnen wird nie
#: gefolgt: eine abgelaufene Session darf keinen Kontakt zu Keycloak/IdP auslösen.
_AUTH_FLOW_MARKERS = (
    "openidconnect",
    "openid-connect",
    "/realms/",
    "shibboleth.sso",
    "saml.php",
)
_DEFAULT_PORTS = {"http": 80, "https": 443}
#: L2: nur diese ILIAS-Cookies werden bei einer Rotation neu gespeichert.
COOKIE_ALLOWLIST = frozenset({"PHPSESSID", "ilClientId"})


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return scheme, (parts.hostname or "").lower(), port or _DEFAULT_PORTS.get(scheme)


def is_auth_redirect(location_url: str, base_url: str) -> bool:
    """True, wenn einer Weiterleitung nicht gefolgt werden darf (Session-Ende, Exit 3).

    Gilt für: ILIAS-Login-Seiten (``login.php``, ``cmd=force_login``, ``reloadpublic=1``),
    den Login-/IdP-Fluss (``openidconnect``, Keycloak ``/realms/…``, Shibboleth/SAML) und
    **jeden anderen Host** als den ILIAS-Host der Instanz (z. B. ``login.hs-heilbronn.de``).
    Reine Funktion, wird vor dem Folgen jeder Weiterleitung geprüft.
    """

    lowered = location_url.lower()
    if any(marker in lowered for marker in _LOGIN_MARKERS + _AUTH_FLOW_MARKERS):
        return True
    _, host, port = _origin(location_url)
    _, base_host, base_port = _origin(base_url)
    if not host:  # relative Angabe ohne Host: bleibt auf der Instanz
        return False
    return host != base_host or port != base_port


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def safe_url(url: str) -> str:
    """URL ohne Query-Werte (für Fehlermeldungen, nie Tokens/Queries ausgeben)."""

    parts = urlsplit(str(url))
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else parts.path


class IliasPage:
    """Antwort einer ILIAS-GET-Anfrage (HTML + finale URL + Status)."""

    def __init__(self, html: str, url: str, status: int) -> None:
        self.html = html
        self.url = url
        self.status = status


class Fetcher:
    """Wiederverwendbarer GET-Fetcher mit Session, Pause und Crawl-Schutz."""

    def __init__(
        self,
        config: Config,
        store: SessionStore,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.base_url = config.normalized_base_url
        self.key = config.instance
        self.request_count = 0
        self.max_requests = _env_int("ILIAS_CLI_MAX_REQUESTS", DEFAULT_MAX_REQUESTS)
        self.interval = _env_float("ILIAS_CLI_REQUEST_INTERVAL", DEFAULT_REQUEST_INTERVAL)
        self._client = client or self._build_client()
        self._cookies = self.store.load()
        if not self._cookies:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.key}.",
                hint=f"Erst `ilias login --instance {self.key}` (oder `ilias setup --instance {self.key}`) ausführen.",
            )
        host = urlsplit(self.base_url).hostname or ""
        for name, value in self._cookies.items():
            self._client.cookies.set(name, value, domain=host)

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            follow_redirects=False,
            timeout=DEFAULT_TIMEOUT,
            headers={
                "User-Agent": user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            trust_env=False,
            event_hooks=debuglog.EVENT_HOOKS,
        )

    def close(self) -> None:
        self._client.close()

    # -- Anfrage --------------------------------------------------------
    def get(self, url: str, *, label: str = "Seite", expect_ref: int | None = None) -> IliasPage:
        current = urljoin(self.base_url + "/", url)
        for _ in range(MAX_REDIRECTS + 1):
            response = self._send(current, label)
            status = response.status_code
            if 300 <= status < 400:
                location = response.headers.get("location") or ""
                if not location:
                    raise ParserError(f"{label}: Weiterleitung ohne Ziel ({safe_url(current)}).")
                target = urljoin(str(response.url), location)
                if is_auth_redirect(target, self.base_url):
                    raise self._session_expired(label)
                current = target
                continue
            try:
                page = self._classify(response, label, expect_ref)
            except PermissionDeniedError:
                self._store_rotated()  # Session ist gültig, nur das Objekt nicht lesbar
                raise
            self._store_rotated()
            return page
        raise NetworkError(
            f"{label}: zu viele Weiterleitungen ({safe_url(url)}).",
            hint=f"ILIAS-Adresse prüfen oder `ilias status --instance {self.key}`.",
        )

    def _send(self, url: str, label: str) -> httpx.Response:
        if self.request_count >= self.max_requests:
            raise CrawlLimitError(
                f"{label}: Request-Obergrenze {self.max_requests} erreicht (crawl_limit).",
                hint=(
                    "`ILIAS_CLI_MAX_REQUESTS` erhöhen oder `--depth` begrenzen "
                    f"(`ilias ls <kurs> --instance {self.key}`)."
                ),
            )
        self.request_count += 1
        if self.interval > 0:
            time.sleep(self.interval)
        try:
            response = self._client.get(url)
        except httpx.RequestError as exc:
            raise NetworkError(
                f"{label}: Verbindung fehlgeschlagen ({type(exc).__name__}, {safe_url(url)}).",
                hint=f"Erreichbarkeit von {self.base_url} prüfen (ggf. VPN).",
            ) from None
        if response.status_code >= 500:
            raise NetworkError(
                f"{label}: Serverfehler HTTP {response.status_code} ({safe_url(url)}).",
                hint=f"Später erneut versuchen; `ilias status --instance {self.key}` prüft die Session.",
            )
        return response

    def _classify(self, response: httpx.Response, label: str, expect_ref: int | None) -> IliasPage:
        html = response.text
        if is_ilias_login_page(html):
            raise self._session_expired(label)
        soup = BeautifulSoup(html, "html.parser")
        if soup.select_one(ALERT_DANGER_SELECTOR) is not None:
            raise PermissionDeniedError(
                f"{label}: keine Berechtigung oder Objekt nicht vorhanden ({safe_url(response.url)}).",
                hint=f"Mitgliedschaft mit `ilias courses --instance {self.key}` prüfen.",
            )
        final_ref = _ref_id_from_url(str(response.url))
        if expect_ref is not None and final_ref is not None and final_ref != expect_ref:
            raise PermissionDeniedError(
                f"{label}: Anfrage auf ref_id {expect_ref} endete bei ref_id {final_ref} ({safe_url(response.url)}).",
                hint=f"Mitgliedschaft mit `ilias courses --instance {self.key}` prüfen.",
            )
        return IliasPage(html=html, url=str(response.url), status=response.status_code)

    def _store_rotated(self) -> None:
        """Neue Allowlist-Cookie-Werte (Rotation) übernehmen und speichern.

        Andere gespeicherte Cookies bleiben unverändert; Keycloak-/Fremd-Cookies werden
        nie übernommen (``ilias_cookies`` filtert auf den ILIAS-Host). Nur bei einer
        echten Änderung wird geschrieben.
        """

        current = ilias_cookies(self._client, self.base_url)
        rotated = {
            name: value
            for name, value in current.items()
            if name in COOKIE_ALLOWLIST and value and self._cookies.get(name) != value
        }
        if not rotated:
            return
        self._cookies = {**self._cookies, **rotated}
        self.store.save(self._cookies)

    def _session_expired(self, label: str) -> SessionExpiredError:
        return SessionExpiredError(
            f"{label}: Session abgelaufen (Weiterleitung/Anmeldeseite).",
            hint=(
                f"`ilias login --instance {self.key}` oder `ilias setup --instance {self.key}` "
                "ausführen (kein automatischer Re-Login)."
            ),
        )


def _ref_id_from_url(url: str) -> int | None:
    from urllib.parse import parse_qs

    query = parse_qs(urlsplit(url).query)
    raw = (query.get("ref_id") or [""])[0]
    return int(raw) if raw.isdigit() else None
