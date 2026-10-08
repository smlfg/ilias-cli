"""Moodle-Backend über den offiziellen Moodle Mobile Web Service.

Ablauf (siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):
  1. ``POST {base}/login/token.php`` mit ``username``, ``password``,
     ``service=moodle_mobile_app`` -> ``{"token": ...}`` oder
     ``{"error": ..., "errorcode": "invalidlogin"}``.
  2. ``POST {base}/webservice/rest/server.php`` mit ``wstoken``,
     ``wsfunction=core_webservice_get_site_info``, ``moodlewsrestformat=json``
     -> Site-Info oder ``{"errorcode": "invalidtoken"}``.

Der Token wird erst nach erfolgreicher Verifikation gespeichert. Passwort und
Token tauchen in keiner Fehlermeldung auf.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import InstanceConfig
from ..errors import (
    AuthError,
    NetworkError,
    SessionExpiredError,
    UnexpectedResponseError,
)
from ..models import SiteInfo

USER_AGENT = "ilias-cli/0.1.0"
MOODLE_MOBILE_SERVICE = "moodle_mobile_app"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"

_AUTH_MESSAGES = {
    "invalidlogin": "Benutzername oder Passwort ist falsch.",
    "invalidloginattuserclass": "Login für diese Rolle nicht erlaubt.",
    "usernotloggedin": "Login abgelehnt.",
    "usernotactive": "Das Konto ist nicht aktiv.",
    "suspended": "Das Konto ist gesperrt.",
}


class MoodleBackend:
    def __init__(
        self,
        config: InstanceConfig,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        self._owns_client = client is None

    # -- öffentliche API -------------------------------------------------
    def get_token(self, username: str, password: str) -> str:
        url = f"{self.base_url}/login/token.php"
        payload = self._post_form(
            url,
            {
                "username": username,
                "password": password,
                "service": MOODLE_MOBILE_SERVICE,
            },
        )
        if not isinstance(payload, dict):
            raise UnexpectedResponseError(
                "Unerwartete Antwort der Moodle-Anmeldung (kein JSON-Objekt)."
            )
        token = payload.get("token")
        if token:
            return str(token)
        errorcode = str(payload.get("errorcode") or "")
        if errorcode or "error" in payload:
            raise AuthError(_auth_message(errorcode, payload.get("error")))
        raise UnexpectedResponseError("Unerwartete Antwort der Moodle-Anmeldung (kein Token).")

    def get_site_info(self, token: str) -> SiteInfo:
        url = f"{self.base_url}/webservice/rest/server.php"
        payload = self._post_form(
            url,
            {
                "wstoken": token,
                "wsfunction": SITE_INFO_FUNCTION,
                "moodlewsrestformat": "json",
            },
        )
        if not isinstance(payload, dict):
            raise UnexpectedResponseError("Unerwartete Site-Info-Antwort (kein JSON-Objekt).")

        errorcode = str(payload.get("errorcode") or "")
        if errorcode:
            if errorcode == "invalidtoken":
                raise SessionExpiredError("Moodle-Token ist ungültig oder abgelaufen.")
            raise UnexpectedResponseError(
                f"Moodle meldet einen Fehler ({errorcode})."
            )
        if "sitename" not in payload or "username" not in payload:
            raise UnexpectedResponseError("Site-Info ist unvollständig.")

        return SiteInfo(
            sitename=str(payload.get("sitename") or ""),
            username=str(payload.get("username") or ""),
            fullname=str(payload.get("fullname") or ""),
            userid=_as_int(payload.get("userid")),
            siteurl=str(payload.get("siteurl") or "") or None,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # -- HTTP ------------------------------------------------------------
    def _post_form(self, url: str, data: dict[str, str]) -> Any:
        try:
            response = self._client.post(url, data=data)
        except httpx.HTTPError as exc:
            raise NetworkError(
                f"Netzwerkfehler beim Kontakt mit {self.base_url} ({exc.__class__.__name__})."
            ) from None

        if response.status_code >= 500:
            raise NetworkError(
                f"Moodle-Server meldet HTTP {response.status_code}."
            )
        if response.status_code >= 400:
            raise UnexpectedResponseError(
                f"Moodle-Server meldet HTTP {response.status_code}."
            )
        try:
            return response.json()
        except ValueError:
            raise UnexpectedResponseError(
                "Moodle-Server lieferte kein gültiges JSON (unerwartete Antwort)."
            ) from None


def _auth_message(errorcode: str, fallback: Any) -> str:
    if errorcode in _AUTH_MESSAGES:
        return _AUTH_MESSAGES[errorcode]
    if errorcode:
        return f"Moodle-Login abgelehnt ({errorcode})."
    if fallback:
        return "Moodle-Login abgelehnt."
    return "Moodle-Login abgelehnt."


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
