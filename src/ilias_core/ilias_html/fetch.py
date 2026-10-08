"""Kleiner Read-Only GET-Helfer für ILIAS mit Session, Status/Redirect-Prüfung.

Spec §4.3, §7: Session laden, GET-only, User-Agent, Pause, Prüfreihenfolge:
1. Verbindung fehlgeschlagen -> Exit 4
2. HTTP >= 500 -> Exit 4
3. Redirect-Kette endet auf login.php/cmd=force_login/reloadpublic=1, Login-Formular,
   oder Metabar mit login.php-Link statt logout.php -> Exit 3 (session_expired)
4. .alert-danger im Hauptinhalt -> Exit 1 (permission_denied)
5. Erwartete Struktur fehlt -> Exit 5 (parse_error)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import Config
from ..errors import NetworkError, NotLoggedInError, ParserError, SessionExpiredError
from ..http import build_client
from ..session import SessionStore


@dataclass(frozen=True)
class FetchResult:
    """Ergebnis eines GET-Requests mit Metadaten."""
    html: str
    url: str
    status_code: int
    cookies: dict[str, str]


def _request_interval() -> float:
    """Lese ILIAS_CLI_REQUEST_INTERVAL (Default 1.0s, Tests setzen 0)."""
    try:
        return float(os.environ.get("ILIAS_CLI_REQUEST_INTERVAL", "1.0"))
    except ValueError:
        return 1.0


_last_request_time: float = 0.0


def _respect_interval() -> None:
    """Warte gemäß Request-Intervall."""
    global _last_request_time
    interval = _request_interval()
    if interval <= 0:
        return
    elapsed = time.time() - _last_request_time
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request_time = time.time()


def _load_session_cookies(config: Config) -> dict[str, str]:
    """Lade gespeicherte Session-Cookies."""
    store = SessionStore(config)
    cookies = store.load()
    if not cookies:
        raise NotLoggedInError(
            "Nicht eingeloggt. Bitte zuerst `ilias login` ausführen.",
            hint=f"`ilias login --instance {config.key}` oder `ilias setup --instance {config.key}` ausführen.",
        )
    return cookies


def _check_redirect_chain(response: httpx.Response, config: Config) -> None:
    """Prüfe Redirect-Kette auf Login-Indikatoren (Exit 3).

    Spec §7: Redirect-Kette endet auf login.php / cmd=force_login / reloadpublic=1,
    ein Login-Formular, oder eine Metabar mit login.php-Link statt logout.php.
    """
    # Finale URL prüfen
    final_url = str(response.url)
    parsed = urlparse(final_url)

    # Pfad endet auf login.php
    if parsed.path.endswith("login.php"):
        raise SessionExpiredError(
            "Session abgelaufen (Weiterleitung zur Anmeldeseite).",
            hint=f"`ilias login --instance {config.key}` oder `ilias setup --instance {config.key}` ausführen.",
        )

    # Query enthält cmd=force_login oder reloadpublic=1
    query = parsed.query.lower()
    if "cmd=force_login" in query or "reloadpublic=1" in query:
        raise SessionExpiredError(
            "Session abgelaufen (erzwungener Login).",
            hint=f"`ilias login --instance {config.key}` oder `ilias setup --instance {config.key}` ausführen.",
        )

    # HTML auf Login-Formular oder Metabar mit login.php prüfen
    html = response.text
    if _has_login_form(html) or _has_login_metabar(html, config.normalized_base_url):
        raise SessionExpiredError(
            "Session abgelaufen (Anmeldeseite oder Login-Metabar erkannt).",
            hint=f"`ilias login --instance {config.key}` oder `ilias setup --instance {config.key}` ausführen.",
        )


def _has_login_form(html: str) -> bool:
    """Prüfe auf Keycloak/ILIAS Login-Formular."""
    soup = BeautifulSoup(html, "html.parser")
    # Keycloak-Formular
    if soup.select_one("#kc-form-login"):
        return True
    # ILIAS-Login-Formular
    if soup.select_one('form[action*="login.php"]'):
        return True
    return False


def _has_login_metabar(html: str, base_url: str) -> bool:
    """Prüfe auf Metabar mit login.php-Link statt logout.php (Spec §13.7)."""
    soup = BeautifulSoup(html, "html.parser")
    metabar = soup.select_one(".il-maincontrols-metabar")
    if not metabar:
        return False
    # login.php Link vorhanden?
    login_link = metabar.select_one('a[href*="login.php"]')
    logout_link = metabar.select_one('a[href*="logout.php"]')
    return login_link is not None and logout_link is None


def _check_permission_denied(html: str, requested_url: str, base_url: str) -> None:
    """Prüfe auf 'keine Berechtigung' (.alert-danger im Hauptinhalt) -> Exit 1.

    Spec §13.7: HHN antwortet nicht mit Fehlerseite, sondern 302 auf Repository-Wurzel.
    Dort steht .alert-danger über einer Kategorienliste.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Hauptinhalt: #ilContentContainer
    main_content = soup.select_one("#ilContentContainer")
    if not main_content:
        main_content = soup

    alert_danger = main_content.select_one(".alert-danger")
    if alert_danger:
        text = alert_danger.get_text().lower()
        if "berechtigung" in text or "zugriff" in text:
            raise ParserError(
                f"Keine Berechtigung für {requested_url}.",
                hint="Prüfen Sie, ob Sie Mitglied des Kurses/Gruppe sind.",
            )


def _check_expected_structure(html: str, page_type: str, url: str) -> None:
    """Prüfe, ob erwartete Struktur vorhanden ist, sonst Exit 5.

    Spec §7: erwartete Struktur fehlt -> Exit 5 parse_error
    (Meldung nennt Seitentyp und URL ohne Query-Werte)
    """
    parsed = urlparse(url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    soup = BeautifulSoup(html, "html.parser")

    if page_type == "membership":
        # Meine Kurse und Gruppen: #ilContentContainer .panel-body mit il-item-group
        if not soup.select_one("#ilContentContainer .panel-body"):
            raise ParserError(
                f"Unerwartetes HTML für {page_type} ({clean_url}): Hauptcontainer fehlt.",
                hint="ILIAS-Seitenstruktur hat sich geändert.",
            )
    elif page_type == "container":
        # Kurs/Ordner/Gruppe: #ilContentContainer #il_center_col mit ilContainerBlock
        if not soup.select_one("#ilContentContainer #il_center_col"):
            raise ParserError(
                f"Unerwartetes HTML für {page_type} ({clean_url}): Container-Inhalt fehlt.",
                exit_code=5,
                hint="ILIAS-Seitenstruktur hat sich geändert.",
            )


def fetch_page(config: Config, path: str, *, page_type: str = "unknown") -> FetchResult:
    """Führe GET-Request mit Session und allen Prüfungen durch.

    Args:
        config: Instanz-Konfiguration
        path: Pfad relativ zur base_url (z. B. "/ilias.php?baseClass=ilmembershipoverviewgui")
        page_type: Seitentyp für Struktur-Prüfung ("membership", "container", etc.)

    Returns:
        FetchResult mit HTML, URL, Status, Cookies

    Raises:
        NotLoggedInError: Keine Session (Exit 2)
        IliasFetchError: Mit exit_code und hint für alle anderen Fehlerklassen
        NetworkError: Verbindungsfehler / HTTP >= 500 (Exit 4)
    """
    _respect_interval()

    cookies = _load_session_cookies(config)
    client = build_client(config, follow_redirects=True)

    base_url = config.normalized_base_url
    full_url = base_url + path

    # Cookies setzen
    host = urlparse(base_url).hostname or ""
    for name, value in cookies.items():
        client.cookies.set(name, value, domain=host)

    try:
        response = client.get(full_url)
    except httpx.RequestError as exc:
        raise NetworkError(
            f"Verbindung zu {base_url} fehlgeschlagen: {type(exc).__name__}.",
            hint=f"Erreichbarkeit von {base_url} prüfen (ggf. VPN).",
        ) from None

    # HTTP >= 500 -> Exit 4
    if response.status_code >= 500:
        raise NetworkError(f"Serverfehler HTTP {response.status_code} von {base_url}.")

    # Redirect-Kette auf Login prüfen -> Exit 3
    _check_redirect_chain(response, config)

    # HTML laden
    html = response.text

    # Berechtigung prüfen -> Exit 1
    _check_permission_denied(html, full_url, base_url)

    # Erwartete Struktur prüfen -> Exit 5
    _check_expected_structure(html, page_type, full_url)

    # Cookies aktualisieren (falls ILIAS PHPSESSID rotiert)
    new_cookies = {}
    for cookie in client.cookies.jar:
        if cookie.domain and (cookie.domain == host or host.endswith("." + cookie.domain)):
            new_cookies[cookie.name] = cookie.value or ""

    return FetchResult(
        html=html,
        url=str(response.url),
        status_code=response.status_code,
        cookies=new_cookies,
    )