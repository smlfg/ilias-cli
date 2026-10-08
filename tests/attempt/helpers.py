"""Gemeinsame Test-Helfer: realistische HTML-Fixtures und Mock-Routen."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

BASE = "https://ilias.hs-heilbronn.de"
KEYCLOAK = "https://login.hs-heilbronn.de"

OPENIDC_URL = f"{BASE}/openidconnect.php"
AUTH_URL = (
    f"{KEYCLOAK}/realms/hhn/protocol/openid-connect/auth"
    "?client_id=hhn_common_ilias&state=state-123"
)
AUTH_PATH = f"{KEYCLOAK}/realms/hhn/login-actions/authenticate"
LOGIN_ACTION = (
    f"{AUTH_PATH}"
    "?session_code=abc123session&execution=def456execution"
    "&client_id=hhn_common_ilias&tab_id=ghi789tab"
)
TOTP_ACTION = (
    f"{AUTH_PATH}"
    "?session_code=abc123session&execution=mno345execution"
    "&client_id=hhn_common_ilias&tab_id=ghi789tab"
)
CALLBACK_URL = f"{BASE}/openidconnect.php?code=XYZ&state=state-123"
DASHBOARD_URL = f"{BASE}/ilias.php?baseClass=ilDashboardGUI"
LOGIN_PHP_URL = f"{BASE}/login.php?client_id=iliashhn"

_EXECUTION_TOTP = "mno345execution"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def html_response(name: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=fixture(name),
        headers={"content-type": "text/html; charset=utf-8"},
    )


def start_openidc(router, *, set_client_cookie: bool = True):
    headers = {"location": AUTH_URL}
    if set_client_cookie:
        headers["set-cookie"] = "ilClientId=iliashhn; Path=/"
    return router.get(OPENIDC_URL).mock(return_value=httpx.Response(302, headers=headers))


def keycloak_login(router):
    return router.get(AUTH_URL).mock(
        return_value=html_response("keycloak_login.html")
    )


def keycloak_totp(router):
    return router.get(AUTH_URL).mock(
        return_value=html_response("keycloak_totp.html")
    )


def mock_authenticate(router, handler):
    """Registriert den Keycloak-POST-Endpunkt und unterscheidet per ``execution``."""

    return router.post(url__regex=re.escape(AUTH_PATH) + r".*").mock(side_effect=handler)


def mock_successful_login(router):
    """Vollständiger Erfolgs-Flow inkl. TOTP. Gibt die Routen zurück."""

    routes = {}
    # Wichtig: gleicher Pfad wie openidconnect.php, daher zuerst und mit
    # expliziten Query-Parametern registrieren.
    routes["callback"] = router.get(
        BASE + "/openidconnect.php", params={"code": "XYZ", "state": "state-123"}
    ).mock(
        return_value=httpx.Response(
            302,
            headers={
                "location": DASHBOARD_URL,
                "set-cookie": "PHPSESSID=super-secret-session; Path=/",
            },
        )
    )
    routes["openidc"] = start_openidc(router)
    routes["auth"] = keycloak_login(router)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("execution") == _EXECUTION_TOTP:
            return httpx.Response(302, headers={"location": CALLBACK_URL})
        return html_response("keycloak_totp.html")

    routes["authenticate"] = mock_authenticate(router, handler)
    routes["dashboard"] = router.get(DASHBOARD_URL).mock(
        return_value=html_response("ilias_dashboard.html")
    )
    return routes


def mock_wrong_password(router):
    routes = {}
    routes["openidc"] = start_openidc(router)
    routes["auth"] = keycloak_login(router)
    routes["authenticate"] = mock_authenticate(
        router, lambda request: html_response("keycloak_login_error.html")
    )
    return routes


def mock_wrong_totp(router):
    routes = {}
    routes["openidc"] = start_openidc(router)
    routes["auth"] = keycloak_login(router)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("execution") == _EXECUTION_TOTP:
            return html_response("keycloak_totp_error.html")
        return html_response("keycloak_totp.html")

    routes["authenticate"] = mock_authenticate(router, handler)
    return routes


def mock_unexpected_after_credentials(router):
    routes = {}
    routes["openidc"] = start_openidc(router)
    routes["auth"] = keycloak_login(router)
    routes["authenticate"] = mock_authenticate(
        router,
        lambda request: httpx.Response(200, text="<html><body>???</body></html>"),
    )
    return routes


def mock_dashboard_for_status(router):
    return router.get(DASHBOARD_URL).mock(
        return_value=html_response("ilias_dashboard.html")
    )


def mock_expired_session(router):
    router.get(DASHBOARD_URL).mock(
        return_value=httpx.Response(302, headers={"location": LOGIN_PHP_URL})
    )
    router.get(LOGIN_PHP_URL).mock(
        return_value=html_response("ilias_login.php")
    )
