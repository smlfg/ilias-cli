from __future__ import annotations

from typing import Callable

import httpx

from . import __version__
from .errors import AuthError, NetworkError, ParserError
from .keycloak_parser import (
    parse_error_message,
    parse_login_form,
    parse_totp_form,
)
from .models import SessionData

USER_AGENT = f"ilias-cli/{__version__}"
DEFAULT_TIMEOUT = 20.0
MAX_REDIRECTS = 15


def make_client(cookies: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(
        follow_redirects=False,
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        cookies=cookies,
    )


def _wrap_network(fn: Callable[[], httpx.Response]) -> httpx.Response:
    try:
        return fn()
    except httpx.HTTPError as exc:
        raise NetworkError(f"Netzwerk-/Serverfehler: {type(exc).__name__}") from exc


def login(
    base_url: str,
    username: str,
    password: str,
    totp_provider: Callable[[], str],
    *,
    client: httpx.Client | None = None,
) -> SessionData:
    own_client = client is None
    c = client or make_client()
    try:
        start = _wrap_network(lambda: c.get(f"{base_url}/openidconnect.php"))
        current = _follow_redirect(c, start)
        if current.status_code != 200:
            raise ParserError(f"Unerwartete Antwort beim Laden der Keycloak-Seite (HTTP {current.status_code})")
        form = parse_login_form(current.text)
        if form is None:
            err = parse_error_message(current.text)
            if err:
                raise AuthError(err)
            raise ParserError("Erwartetes Keycloak-Loginformular nicht gefunden")

        payload = dict(form.hidden)
        payload["username"] = username
        payload["password"] = password
        if "credentialId" in form.fields:
            payload.setdefault("credentialId", "")
        resp = _wrap_network(lambda: c.post(form.action, data=payload))
        current = _handle_post_result(c, resp)

        otp_form = parse_totp_form(current.text) if current.status_code == 200 else None
        if otp_form is None:
            if current.status_code == 200:
                err = parse_error_message(current.text)
                if err:
                    raise AuthError("Login fehlgeschlagen (Benutzername/Passwort ungültig)")
                raise ParserError("Erwartetes Keycloak-TOTP-Formular nicht gefunden")

        otp_payload = dict(otp_form.hidden)
        otp_payload["otp"] = totp_provider()
        resp2 = _wrap_network(lambda: c.post(otp_form.action, data=otp_payload))
        current2 = _handle_post_result(c, resp2)

        if current2.status_code == 200:
            if (
                parse_totp_form(current2.text) is not None
                or parse_login_form(current2.text) is not None
                or parse_error_message(current2.text) is not None
            ):
                raise AuthError("TOTP-Code ungültig")

        cookies = {name: value for name, value in c.cookies.items()}
        if not any(n == "PHPSESSID" for n in cookies):
            raise ParserError("ILIAS-Session-Cookie nicht erhalten")
        return SessionData(base_url=base_url, cookies=cookies)
    finally:
        if own_client:
            c.close()


def _handle_post_result(c: httpx.Client, resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        raise NetworkError(f"Serverfehler (HTTP {resp.status_code})")
    if resp.status_code in (301, 302, 303, 307, 308):
        return _follow_redirect(c, resp)
    return resp


def _follow_redirect(c: httpx.Client, resp: httpx.Response) -> httpx.Response:
    count = 0
    while resp.status_code in (301, 302, 303, 307, 308):
        count += 1
        if count > MAX_REDIRECTS:
            raise ParserError("Zu viele Weiterleitungen")
        location = resp.headers.get("location")
        if not location:
            raise ParserError("Weiterleitung ohne Location-Header")
        url = str(httpx.URL(resp.request.url).join(location))
        resp = _wrap_network(lambda: c.get(url))
    return resp
