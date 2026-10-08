"""Moodle-Backend: token.php + core_webservice_get_site_info (httpx)."""

from __future__ import annotations

import httpx

from .errors import AuthFailedError, NetworkError, ParseError, SessionExpiredError
from .models import SiteInfo


def user_agent() -> str:
    try:
        from ilias_core import __version__

        ver = __version__
    except Exception:
        ver = "0.0.0"
    return f"ilias-cli/{ver}"


def _client(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent()},
    )


def _is_json_response(resp: httpx.Response) -> bool:
    ctype = resp.headers.get("content-type", "").lower()
    if "json" in ctype:
        return True
    # Moodle antwortet JSON auch ohne perfekten Content-Type; anhand des Bodys raten.
    text = resp.text.lstrip()[:1]
    return text in ("{", "[")


def request_token(base_url: str, username: str, password: str, timeout: float = 15.0) -> str:
    """POST {base}/login/token.php. Gibt Token zurück. Keine Secrets in Fehlermeldungen."""
    url = base_url.rstrip("/") + "/login/token.php"
    try:
        with _client(timeout) as client:
            resp = client.post(
                url,
                data={"username": username, "password": password, "service": "moodle_mobile_app"},
            )
    except httpx.TimeoutException:
        raise NetworkError("Netzwerkfehler: Zeitüberschreitung beim Login.")
    except httpx.TransportError:
        raise NetworkError("Netzwerkfehler: Server nicht erreichbar.")
    except NetworkError:
        raise
    except Exception:
        raise NetworkError("Netzwerkfehler: Server nicht erreichbar.")

    if resp.status_code >= 500:
        raise NetworkError(f"Serverfehler (HTTP {resp.status_code}) beim Login.")
    try:
        obj = resp.json()
    except Exception:
        raise ParseError("Unerwartete Antwort des Servers (kein JSON).")
    if not isinstance(obj, dict):
        raise ParseError("Unerwartete Antwort des Servers.")
    token = obj.get("token")
    if isinstance(token, str) and token:
        return token
    errorcode = str(obj.get("errorcode", "") or "")
    error = str(obj.get("error", "") or "")
    if errorcode or error or "error" in obj or "exception" in obj:
        # Klare Meldung ohne Secrets.
        if errorcode in ("invalidlogin", "authloginfailed", "enablemobilewebservice", "missingparam"):
            detail = error or "Benutzername oder Passwort ist falsch."
            raise AuthFailedError(f"Login fehlgeschlagen ({errorcode or 'auth_error'}): {detail}")
        raise AuthFailedError(f"Login fehlgeschlagen ({errorcode or 'auth_error'}): {error or 'Anmeldung abgelehnt.'}")
    raise ParseError("Unerwartete Antwort des Servers.")


def fetch_site_info(base_url: str, token: str, timeout: float = 15.0) -> SiteInfo:
    """POST {base}/webservice/rest/server.php mit core_webservice_get_site_info."""
    url = base_url.rstrip("/") + "/webservice/rest/server.php"
    try:
        with _client(timeout) as client:
            resp = client.post(
                url,
                data={
                    "wstoken": token,
                    "wsfunction": "core_webservice_get_site_info",
                    "moodlewsrestformat": "json",
                },
            )
    except httpx.TimeoutException:
        raise NetworkError("Netzwerkfehler: Zeitüberschreitung bei der Sitzungsprüfung.")
    except httpx.TransportError:
        raise NetworkError("Netzwerkfehler: Server nicht erreichbar.")
    except Exception:
        raise NetworkError("Netzwerkfehler: Server nicht erreichbar.")

    if resp.status_code >= 500:
        raise NetworkError(f"Serverfehler (HTTP {resp.status_code}) bei der Sitzungsprüfung.")
    try:
        obj = resp.json()
    except Exception:
        raise ParseError("Unerwartete Antwort des Servers (kein JSON).")
    if not isinstance(obj, dict):
        raise ParseError("Unerwartete Antwort des Servers.")
    if "exception" in obj or "errorcode" in obj:
        errorcode = str(obj.get("errorcode", ""))
        message = str(obj.get("message", "") or obj.get("error", "") or "")
        if errorcode == "invalidtoken":
            raise SessionExpiredError("Sitzung abgelaufen (ungültiges Token). Bitte erneut einloggen.")
        raise ParseError(f"Unerwartete Antwort des Servers ({errorcode or 'webservice_error'}).")
    try:
        sitename = str(obj.get("sitename", "") or "")
        username = str(obj.get("username", "") or "")
        fullname = str(obj.get("fullname", "") or "")
        userid = obj.get("userid", "")
        if not sitename or not username:
            raise KeyError("missing fields")
    except Exception:
        raise ParseError("Unerwartete Antwort des Servers (site_info unvollständig).")
    return SiteInfo(sitename=sitename, username=username, fullname=fullname, userid=userid)


def login_and_verify(base_url: str, username: str, password: str, timeout: float = 15.0) -> tuple[str, SiteInfo]:
    """Token holen und sofort per site_info verifizieren. Gibt (token, info) zurück."""
    token = request_token(base_url, username, password, timeout=timeout)
    info = fetch_site_info(base_url, token, timeout=timeout)
    return token, info
