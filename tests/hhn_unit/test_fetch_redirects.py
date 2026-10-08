"""Redirect-Härtung des ILIAS-GET-Helfers (``ilias_core.ilias_html.fetch``).

Einer Weiterleitung auf einen anderen Host als den ILIAS-Host der Instanz oder in den
Login-Fluss (``openidconnect``, Keycloak) wird nie gefolgt; das ist wie ``login.php``
der Session-abgelaufen-Pfad (Exit 3). Nur gegen den lokalen Fake (127.0.0.1), nur
synthetische Daten.
"""

from __future__ import annotations

import urllib.parse

import pytest
from hhn.fake_hhn import HhnWorld

from ilias_core.config import Config
from ilias_core.errors import SessionExpiredError
from ilias_core.ilias_html.fetch import Fetcher, is_auth_redirect

BASE = "https://ilias.example.org"


@pytest.mark.parametrize(
    "target",
    [
        "https://login.example.org/realms/hhn/protocol/openid-connect/auth?client_id=x",
        "https://other.example.net/ilias.php?ref_id=1",
        "http://ilias.example.org:8443/ilias.php?ref_id=1",  # anderer Port = anderer Host
        f"{BASE}/openidconnect.php",
        f"{BASE}/login.php?cmd=force_login",
        f"{BASE}/ilias.php?baseClass=ilrepositorygui&reloadpublic=1",
        f"{BASE}/Shibboleth.sso/Login?target=x",
    ],
)
def test_is_auth_redirect_stops(target):
    assert is_auth_redirect(target, BASE) is True


@pytest.mark.parametrize(
    "target",
    [
        f"{BASE}/ilias.php?baseClass=ilrepositorygui&ref_id=900101",
        "https://ILIAS.example.org:443/go/fold/900201",
        "/ilias.php?baseClass=ilrepositorygui&ref_id=900101",
    ],
)
def test_is_auth_redirect_allows_same_host(target):
    assert is_auth_redirect(target, BASE) is False


class _Store:
    """Minimaler Session-Speicher mit einer (beim Fake ungültigen) Session."""

    def load(self):
        return {"PHPSESSID": "expired-session-0000"}


@pytest.fixture
def world():
    w = HhnWorld(username="test.user", password="not-a-real-password", totp="000000").start()
    yield w
    w.stop()


def _fetcher(world: HhnWorld, monkeypatch) -> Fetcher:
    monkeypatch.setenv("ILIAS_CLI_REQUEST_INTERVAL", "0")
    config = Config(base_url=world.ilias_base, instance="hhn")
    return Fetcher(config, _Store())


def test_redirect_to_other_host_keycloak_not_followed(world, monkeypatch):
    """Abgelaufene Session -> ILIAS leitet direkt zu Keycloak (anderer Host/Port): Exit 3, kein Keycloak-Kontakt."""

    def to_keycloak(handler, target: str = "") -> None:
        handler._redirect(
            f"{world.kc_base}/realms/hhn/protocol/openid-connect/auth?client_id=x&state={urllib.parse.quote(target)}"
        )

    monkeypatch.setattr(world, "_login_redirect", to_keycloak)
    fetcher = _fetcher(world, monkeypatch)
    with pytest.raises(SessionExpiredError) as excinfo:
        fetcher.get("/go/crs/900101", label="Kursseite")
    assert "--instance hhn" in (excinfo.value.hint or "")
    assert world.requests_to("keycloak") == []
    assert fetcher.request_count == 1


def test_redirect_to_openidconnect_on_ilias_host_not_followed(world, monkeypatch):
    """Weiterleitung auf ``/openidconnect.php`` (gleicher Host) startet den Login-Fluss: Exit 3, nicht folgen."""

    monkeypatch.setattr(
        world, "_login_redirect", lambda handler, target="": handler._redirect(f"{world.ilias_base}/openidconnect.php")
    )
    fetcher = _fetcher(world, monkeypatch)
    with pytest.raises(SessionExpiredError):
        fetcher.get("/go/crs/900101", label="Kursseite")
    assert not [r for r in world.requests_to("ilias") if "openidconnect" in r.path]
    assert world.requests_to("keycloak") == []
    assert fetcher.request_count == 1
