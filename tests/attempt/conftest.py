"""Fixtures und Mock-Transport-Handler für die Tests (KEINE echten Requests)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

BASE_URL = "https://ilias.example.com"
KC_BASE = "https://login.example.com"
CLIENT_ID = "iliashhn"
KC_AUTH_URL = (
    f"{KC_BASE}/realms/hhn/protocol/openid-connect/auth"
    "?client_id=hhn_common_ilias&response_type=code&scope=openid"
    f"&state=STATE123&redirect_uri={BASE_URL}/openidconnect.php"
)
LOGIN_ACTION = (
    f"{KC_BASE}/realms/hhn/login-actions/authenticate"
    "?session_code=SC1&execution=E1&client_id=hhn_common_ilias&tab_id=T1"
)
TOTP_ACTION = (
    f"{KC_BASE}/realms/hhn/login-actions/authenticate"
    "?session_code=SC1&execution=E2&client_id=hhn_common_ilias&tab_id=T1"
)
DASHBOARD_URL = f"{BASE_URL}/ilias.php?baseClass=ilDashboardGUI"

VALID_USERNAME = "testuser"
VALID_PASSWORD = "testpass"
VALID_OTP = "123456"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture()
def html() -> dict[str, str]:
    """Alle HTML-Fixtures als Dict."""
    return {
        "login": _read("keycloak_login.html"),
        "login_error": _read("keycloak_login_error.html"),
        "totp": _read("keycloak_totp.html"),
        "totp_error": _read("keycloak_totp_error.html"),
        "dashboard": _read("ilias_dashboard.html"),
        "login_page": _read("ilias_login_page.html"),
    }


def _form_data(request: httpx.Request) -> dict[str, str]:
    body = request.content.decode()
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def make_handler(html: dict[str, str]):
    """Baut einen MockTransport-Handler für den kompletten Login-Flow.

    Prüft Credentials gegen VALID_USERNAME/VALID_PASSWORD/VALID_OTP und
    liefert bei Fehlern die jeweiligen Fehler-HTML-Seiten.
    Gibt (handler, requests) zurück; requests sichtbar für Assertions.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = urlparse(str(request.url)).path
        query = parse_qs(urlparse(str(request.url)).query)

        if path == "/openidconnect.php":
            if "code" in query:
                return httpx.Response(302, headers={"location": DASHBOARD_URL})
            return httpx.Response(302, headers={"location": KC_AUTH_URL})

        if path.endswith("/protocol/openid-connect/auth"):
            return httpx.Response(200, html=html["login"])

        if path.endswith("/login-actions/authenticate"):
            if request.method == "GET":
                return httpx.Response(200, html=html["totp"])
            data = _form_data(request)
            if "otp" in data:
                if data["otp"] == VALID_OTP:
                    return httpx.Response(
                        302,
                        headers={
                            "location": f"{BASE_URL}/openidconnect.php?code=CODE&state=STATE123"
                        },
                    )
                return httpx.Response(200, html=html["totp_error"])
            if (
                data.get("username") == VALID_USERNAME
                and data.get("password") == VALID_PASSWORD
            ):
                return httpx.Response(302, headers={"location": TOTP_ACTION})
            return httpx.Response(200, html=html["login_error"])

        if path == "/ilias.php":
            return httpx.Response(
                200,
                html=html["dashboard"],
                headers=[
                    ("set-cookie", "PHPSESSID=sessionabc123; Path=/; HttpOnly"),
                    ("set-cookie", "ilClientId=iliashhn; Path=/; HttpOnly"),
                ],
            )

        return httpx.Response(404, html="<html><body>Not Found</body></html>")

    return handler, requests


@pytest.fixture()
def success_client(html: dict[str, str]) -> tuple[httpx.Client, list[httpx.Request]]:
    """httpx.Client mit MockTransport für den erfolgreichen Login-Flow."""
    handler, requests = make_handler(html)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return client, requests


@pytest.fixture()
def test_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Config-Datei in tmp_path + ILIAS_CLI_CONFIG gesetzt."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'base_url = "{BASE_URL}"\nclient_id = "{CLIENT_ID}"\n', encoding="utf-8"
    )
    monkeypatch.setenv("ILIAS_CLI_CONFIG", str(config_file))
    from ilias_core.config import load_config

    return load_config()


@pytest.fixture()
def memory_store():
    from ilias_core.session.store import InMemorySessionStore

    return InMemorySessionStore()


@pytest.fixture()
def cli_env(test_config, memory_store, monkeypatch: pytest.MonkeyPatch):
    """Patched load_config/SessionManager für login/status/logout (CLI-Tests)."""
    from ilias_core.session.manager import SessionManager

    for mod in ("ilias_cli.commands.login", "ilias_cli.commands.status", "ilias_cli.commands.logout"):
        monkeypatch.setattr(f"{mod}.load_config", lambda: test_config)

    def manager_factory(config):
        return SessionManager(config, store=memory_store)

    for mod in ("ilias_cli.commands.login", "ilias_cli.commands.status", "ilias_cli.commands.logout"):
        monkeypatch.setattr(f"{mod}.SessionManager", manager_factory)

    return memory_store


def save_session(store, cookies: dict, username: str | None = None):
    """Hilfsfunktion: speichert eine SessionData im Store (für Tests)."""
    from datetime import datetime, timezone

    from ilias_core.models import SessionData

    store.save(
        SessionData(
            base_url=BASE_URL,
            client_id=CLIENT_ID,
            cookies=cookies,
            username=username,
            created_at=datetime.now(timezone.utc),
        )
    )
