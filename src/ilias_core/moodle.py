"""Moodle-Backend: Login über Web-Service-Token, Site-Info zur Prüfung."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from . import __version__
from .errors import AuthError, NetworkError, ParserError, SessionExpiredError

_TIMEOUT = 30.0


@dataclass(frozen=True)
class SiteInfo:
    sitename: str
    username: str
    fullname: str
    userid: int | None


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": f"ilias-cli/{__version__}"},
        timeout=_TIMEOUT,
        follow_redirects=False,
    )


def _post_form(url: str, data: dict[str, str]) -> httpx.Response:
    try:
        with _client() as client:
            resp = client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise NetworkError(f"Server nicht erreichbar: {exc.__class__.__name__}") from exc
    if resp.status_code >= 500:
        raise NetworkError(f"Serverfehler (HTTP {resp.status_code})")
    return resp


def _json_object(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError as exc:
        raise ParserError("Unerwartete Antwort (kein JSON)") from exc
    if not isinstance(data, dict):
        raise ParserError("Unerwartete Antwort (kein JSON-Objekt)")
    return data


def request_token(base_url: str, username: str, password: str) -> str:
    resp = _post_form(
        f"{base_url}/login/token.php",
        {"username": username, "password": password, "service": "moodle_mobile_app"},
    )
    data = _json_object(resp)
    token = data.get("token")
    if isinstance(token, str) and token:
        return token
    error = data.get("error")
    if isinstance(error, str):
        hint = data.get("errorcode")
        detail = f" ({hint})" if isinstance(hint, str) else ""
        raise AuthError(f"Login fehlgeschlagen: {error}{detail}")
    raise ParserError("Unerwartete Antwort beim Login")


def get_site_info(base_url: str, token: str) -> SiteInfo:
    resp = _post_form(
        f"{base_url}/webservice/rest/server.php",
        {
            "wstoken": token,
            "wsfunction": "core_webservice_get_site_info",
            "moodlewsrestformat": "json",
        },
    )
    data = _json_object(resp)
    errorcode = data.get("errorcode")
    if errorcode == "invalidtoken" or (errorcode and "token" in str(errorcode)):
        raise SessionExpiredError("Session abgelaufen (invalidtoken)")
    if isinstance(data.get("exception"), str) or isinstance(data.get("error"), str):
        message = data.get("message") or data.get("error") or data.get("exception")
        raise AuthError(f"Abfrage fehlgeschlagen: {message}")
    if isinstance(data.get("sitename"), str):
        return SiteInfo(
            sitename=data["sitename"],
            username=str(data.get("username", "")),
            fullname=str(data.get("fullname", "")),
            userid=data.get("userid") if isinstance(data.get("userid"), int) else None,
        )
    raise ParserError("Unerwartete Antwort bei site_info")
