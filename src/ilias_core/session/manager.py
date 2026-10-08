"""SessionManager: speichern/laden/löschen + Gültigkeitsprüfung (A5)."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from ilias_core.auth.parser import is_login_page
from ilias_core.config import Config
from ilias_core.errors import NetworkError, NotAuthenticatedError
from ilias_core.http import create_client
from ilias_core.models import LoginResult, SessionData, SessionStatus
from ilias_core.session.store import SessionStore, default_store


def _session_expired(resp: httpx.Response, base_url: str) -> bool:
    """True wenn die Antwort auf eine abgelaufene Session hindeutet.

    Indikatoren: Redirect auf ``login.php`` (finaler URL-Pfad) oder ein
    Login-Formular im HTML (Keycloak- oder ILIAS-Login).
    """
    path = urlparse(str(resp.url)).path
    if "login.php" in path:
        return True
    return is_login_page(resp.text)


def check_session(
    base_url: str,
    client_id: str,
    cookies: dict[str, str],
    *,
    client: httpx.Client | None = None,
) -> SessionStatus:
    """Session mit einem Request auf eine geschützte ILIAS-Seite prüfen.

    Redirect auf ``login.php`` (oder Login-Formular im HTML) => abgelaufen.
    Es wird KEIN automatischer Re-Login versucht.
    """
    if client is None:
        client = create_client()
    url = f"{base_url}/ilias.php?baseClass=ilDashboardGUI"
    try:
        resp = client.get(url, cookies=cookies)
    except httpx.HTTPError as exc:
        raise NetworkError(f"Netzwerkfehler beim Prüfen der Session: {exc}") from exc

    checked_at = datetime.now(timezone.utc)
    if _session_expired(resp, base_url):
        return SessionStatus(
            logged_in=False,
            base_url=base_url,
            client_id=client_id,
            checked_at=checked_at,
            message="Session abgelaufen - bitte erneut einloggen (ilias login)",
        )
    return SessionStatus(
        logged_in=True,
        base_url=base_url,
        client_id=client_id,
        checked_at=checked_at,
        message="Eingeloggt",
    )


class SessionManager:
    """Hoch-Level-API für die Session (pro Gerät, kein Cookie-Sync)."""

    def __init__(self, config: Config, store: SessionStore | None = None) -> None:
        self._config = config
        self._store = store if store is not None else default_store(config)

    def save(self, result: LoginResult, username: str | None = None) -> None:
        data = SessionData(
            base_url=self._config.base_url,
            client_id=self._config.client_id,
            cookies=result.cookies,
            username=username,
            created_at=datetime.now(timezone.utc),
        )
        self._store.save(data)

    def load(self) -> SessionData | None:
        return self._store.load()

    def delete(self) -> None:
        self._store.delete()

    def check(self) -> SessionStatus:
        data = self._store.load()
        if data is None:
            raise NotAuthenticatedError(
                "Keine aktive Session - bitte zuerst 'ilias login' ausführen"
            )
        return check_session(data.base_url, data.client_id, data.cookies)
