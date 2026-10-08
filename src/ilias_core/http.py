"""HTTP-Bausteine: eigener User-Agent (N2), keine Redirects, keine Secrets im Fehlertext."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .errors import NetworkError, ParseError

USER_AGENT_PREFIX = "ilias-cli"
DEFAULT_TIMEOUT = 30.0


def user_agent() -> str:
    from . import __version__

    return f"{USER_AGENT_PREFIX}/{__version__}"


class HttpClient:
    """Dünner httpx-Wrapper. `follow_redirects=False`: wir folgen nie blind einem
    Redirect (dort könnten Zugangsdaten oder der Token landen)."""

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": user_agent(), "Accept": "application/json"},
            follow_redirects=False,
            trust_env=False,  # kein Proxy aus der Umgebung: nichts verlässt den Rechner ungefragt
        )

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- Requests -------------------------------------------------------
    def post_form(self, path: str, data: dict[str, str], *, label: str = "Anfrage") -> httpx.Response:
        try:
            response = self._client.post(path, data=data)
        except httpx.RequestError as exc:
            raise NetworkError(
                f"{label} fehlgeschlagen: {type(exc).__name__} ({exc}).",
                hint=f"Erreichbarkeit von {self.base_url} prüfen (ggf. VPN).",
            ) from None
        if response.status_code >= 500:
            raise NetworkError(f"{label}: Serverfehler HTTP {response.status_code} von {self.base_url}.")
        if 300 <= response.status_code < 400:
            raise ParseError(
                f"{label}: unerwartete Weiterleitung (HTTP {response.status_code}) von {self.base_url}.",
                hint="Die Basis-URL dürfte auf die Moodle-Wurzel zeigen (ohne /login/index.php).",
            )
        return response

    def get(self, path: str, *, label: str = "Anfrage") -> httpx.Response:
        try:
            response = self._client.get(path)
        except httpx.RequestError as exc:
            raise NetworkError(f"{label} fehlgeschlagen: {type(exc).__name__} ({exc}).") from None
        if response.status_code >= 500:
            raise NetworkError(f"{label}: Serverfehler HTTP {response.status_code} von {self.base_url}.")
        return response


def json_body(response: httpx.Response, *, label: str) -> dict[str, Any]:
    """JSON-Objekt aus einer Antwort - sonst Parser-Fehler (Exit 5)."""
    text = response.text
    if not text.strip():
        raise ParseError(f"{label}: leere Antwort (HTTP {response.status_code}).")
    if response.status_code >= 400 and not text.lstrip().startswith(("{", "[")):
        raise ParseError(
            f"{label}: unerwartete Antwort (HTTP {response.status_code}, {response.headers.get('Content-Type', 'unbekannter Typ')}).",
            hint="Die Adresse liefert kein JSON - vermutlich falsche Basis-URL oder Wartungsseite.",
        )
    try:
        data = json.loads(text)
    except ValueError:
        raise ParseError(
            f"{label}: Antwort ist kein JSON (HTTP {response.status_code}).",
            hint="Erwartet wird eine JSON-Antwort des Moodle-Webservice.",
        ) from None
    if not isinstance(data, dict):
        raise ParseError(f"{label}: JSON ist kein Objekt (Typ {type(data).__name__}).")
    return data
