"""HTTP-GET-Helfer für ILIAS-Backend: Session laden, GET mit Fehlerprüfung (Spec §7, §13.7).

Lädt gespeicherte Session-Cookies, führt GET aus, prüft in dieser Reihenfolge:
1. Verbindungsfehler -> Exit 4
2. HTTP >= 500 -> Exit 4
3. Redirect-Kette endet auf Login-Seite -> Exit 3
4. .alert-danger im Hauptinhalt -> Exit 1 permission_denied
5. Erwartete Struktur fehlt -> Exit 5 parse_error
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import httpx

from ..config import Instance
from ..errors import NetworkError, NotLoggedInError, ParserError, PermissionDeniedError, SessionExpiredError
from ..http import build_client, user_agent
from ..session import SessionStore

# Seiten-Typen für Fehlermeldungen
PAGE_TYPES = {
    "membership": "Kursübersicht (ilmembershipoverviewgui)",
    "container": "Container-Seite (ilrepositorygui)",
    "dashboard": "Dashboard (ilDashboardGUI)",
    "unknown": "unbekannte Seite",
}


def detect_page_type(url: str) -> str:
    """Seitentyp aus URL bestimmen für Fehlermeldungen."""
    parsed = urlparse(url)
    query = parsed.query.lower()
    if "ilmembershipoverviewgui" in query:
        return PAGE_TYPES["membership"]
    if "ilrepositorygui" in query:
        return PAGE_TYPES["container"]
    if "ildashboardgui" in query:
        return PAGE_TYPES["dashboard"]
    return PAGE_TYPES["unknown"]


def check_response_errors(
    response: httpx.Response,
    page_type: str,
    instance_key: str,
    requested_ref_id: int | None = None,
) -> str:
    """Antwort auf Fehler prüfen (Spec §13.7 Reihenfolge).

    Args:
        response: httpx Response
        page_type: Typ der Seite für Fehlermeldung
        instance_key: Instanz-Schlüssel für Hint
        requested_ref_id: Angeforderte ref_id (für Redirect-Prüfung)

    Returns:
        HTML-Text der Seite

    Raises:
        NetworkError, SessionExpiredError, PermissionDeniedError, ParserError
    """
    # 1. Verbindungsfehler wurden schon beim Request geworfen

    # 2. HTTP >= 500
    if response.status_code >= 500:
        raise NetworkError(
            f"{page_type}: Serverfehler HTTP {response.status_code}.",
            hint=f"Erreichbarkeit von {response.url} prüfen (ggf. VPN).",
        )

    # 3. Redirect-Kette prüfen: endet auf login.php / cmd=force_login / reloadpublic=1
    # oder Login-Formular oder Metabar mit login.php statt logout.php
    final_url = str(response.url)
    if "login.php" in final_url and ("cmd=force_login" in final_url or "reloadpublic=1" in final_url):
        raise SessionExpiredError(
            "Session abgelaufen (Weiterleitung auf Login-Seite).",
            hint=f"`ilias login --instance {instance_key}` oder `ilias setup --instance {instance_key}` ausführen.",
        )

    html = response.text

    # Login-Formular im Inhalt
    if '<form id="kc-form-login"' in html or 'id="kc-otp-login-form"' in html:
        raise SessionExpiredError(
            "Session abgelaufen (Login-Formular statt Inhalt).",
            hint=f"`ilias login --instance {instance_key}` oder `ilias setup --instance {instance_key}` ausführen.",
        )

    # Metabar mit login.php statt logout.php
    # Prüfen ob login.php in einem href vorkommt, aber logout.php nicht
    import re
    has_login_link = bool(re.search(r'href="[^"]*login\.php', html))
    has_logout_link = bool(re.search(r'href="[^"]*logout\.php', html))
    if has_login_link and not has_logout_link:
        raise SessionExpiredError(
            "Session abgelaufen (Anmelde-Link in der Metabar).",
            hint=f"`ilias login --instance {instance_key}` oder `ilias setup --instance {instance_key}` ausführen.",
        )

    # 4. .alert-danger im Hauptinhalt -> permission_denied
    # Hauptinhalt: #ilContentContainer
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    main_content = soup.select_one("#ilContentContainer")
    if main_content and main_content.select_one(".alert-danger"):
        raise PermissionDeniedError(
            "Keine Berechtigung für dieses Objekt.",
            hint=f"`ilias courses --instance {instance_key}` zeigt Ihre Kurse.",
        )

    # Redirect auf andere ref_id als angefragt (Repository-Wurzel = 1)
    if requested_ref_id is not None and requested_ref_id != 1:
        # Prüfen ob auf ref_id=1 weitergeleitet wurde
        if "ref_id=1" in final_url or final_url.endswith("ref_id=1"):
            raise PermissionDeniedError(
                "Keine Berechtigung für dieses Objekt (Weiterleitung auf Magazin-Wurzel).",
                hint=f"`ilias courses --instance {instance_key}` zeigt Ihre Kurse.",
            )

    # 5. Erwartete Struktur prüfen (später im Parser, hier nur HTML zurückgeben)
    return html


def fetch_page(
    instance: Instance,
    url: str,
    *,
    page_type: str = "unknown",
    requested_ref_id: int | None = None,
    session_store: SessionStore | None = None,
) -> str:
    """ILIAS-Seite per GET laden mit vollständiger Fehlerprüfung.

    Args:
        instance: Instanz-Konfiguration
        url: Vollständige URL oder relativer Pfad
        page_type: Seitentyp für Fehlermeldungen
        requested_ref_id: Angeforderte ref_id (für Redirect-Prüfung)
        session_store: SessionStore (wird erstellt falls None)

    Returns:
        HTML-Text der Seite

    Raises:
        NotLoggedInError, NetworkError, SessionExpiredError, PermissionDeniedError, ParserError
    """
    if session_store is None:
        session_store = SessionStore(instance)

    cookies = session_store.load()
    if not cookies:
        raise NotLoggedInError(
            "Nicht eingeloggt. Bitte zuerst `ilias login` ausführen.",
            hint=f"`ilias login --instance {instance.key}` oder `ilias setup --instance {instance.key}`.",
        )

    # Vollständige URL bauen
    if not url.startswith(("http://", "https://")):
        url = f"{instance.base_url.rstrip('/')}/{url.lstrip('/')}"

    client = build_client(instance)
    host = urlparse(instance.base_url).hostname or ""

    try:
        # Cookies setzen
        for name, value in cookies.items():
            client.cookies.set(name, value, domain=host)

        # Request-Pause (ILIAS_CLI_REQUEST_INTERVAL, Default 1.0s, Tests setzen 0)
        interval = float(os.environ.get("ILIAS_CLI_REQUEST_INTERVAL", "1.0"))
        if interval > 0:
            time.sleep(interval)

        # GET ausführen
        response = client.get(url, follow_redirects=True)

        # Fehler prüfen
        return check_response_errors(response, page_type, instance.key, requested_ref_id)

    except httpx.RequestError as exc:
        raise NetworkError(
            f"{page_type}: Verbindungsfehler ({type(exc).__name__}).",
            hint=f"Erreichbarkeit von {instance.base_url} prüfen (ggf. VPN).",
        ) from None
    finally:
        client.close()