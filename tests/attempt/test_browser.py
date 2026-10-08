"""Browser-Fallback (`ilias login --browser`) mit einem Fake-Playwright-Modul."""

from __future__ import annotations

import sys
import types

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core import browser as browser_module
from ilias_core.client import IliasClient
from ilias_core.config import load_config
from ilias_core.errors import AuthenticationError
from ilias_core.session import SessionStore

from helpers import html_response

BASE = "https://ilias.example.invalid"
IDP = "https://idp.example.invalid"
DASHBOARD = f"{BASE}/ilias.php?baseClass=ilDashboardGUI"


class FakePlaywrightError(Exception):
    pass


def install_fake_playwright(monkeypatch, navigation: list[str], cookies: list[dict]) -> dict:
    """Simuliert einen sichtbaren Chromium, in dem sich der Nutzer selbst anmeldet."""

    log: dict = {"goto": [], "headless": None, "closed": False}

    class Page:
        url = ""

        def goto(self, url):
            log["goto"].append(url)
            self.url = url

        def wait_for_url(self, predicate, timeout):
            log["timeout"] = timeout
            for url in navigation:
                self.url = url
                if predicate(url):
                    return
            raise FakePlaywrightError("Timeout")

    class Context:
        def new_page(self):
            return Page()

        def cookies(self):
            return cookies

    class Browser:
        def new_context(self):
            return Context()

        def close(self):
            log["closed"] = True

    class Chromium:
        def launch(self, headless):
            log["headless"] = headless
            return Browser()

    class Manager:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = Manager
    sync_api.Error = FakePlaywrightError
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return log


SAML_NAVIGATION = [
    f"{BASE}/saml.php",
    f"{IDP}/idp/profile/SAML2/Redirect/SSO?execution=e1s1",
    f"{BASE}/Services/Saml/lib/saml2-acs.php/default-sp",
    f"{BASE}/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
]
COOKIES = [
    {"name": "PHPSESSID", "value": "browser-session", "domain": "ilias.example.invalid"},
    {"name": "ilClientId", "value": "ILIAS", "domain": "ilias.example.invalid"},
    {"name": "shib_idp_session", "value": "idp-secret", "domain": "idp.example.invalid"},
    {"name": "JSESSIONID", "value": "idp-java", "domain": ".example.invalid"},
    {"name": "_pk_id", "value": "tracking", "domain": "www.example.invalid"},
]


@pytest.fixture
def mannheim_like(config_dir):
    (config_dir / "config.toml").write_text(
        f'[instances.uni-mannheim]\nbase_url = "{BASE}"\n', encoding="utf-8"
    )
    return load_config(instance="uni-mannheim")


def test_browser_starts_at_saml_and_keeps_only_ilias_cookies(monkeypatch):
    log = install_fake_playwright(monkeypatch, SAML_NAVIGATION, COOKIES)
    cookies = browser_module.login_with_browser(BASE, start_path="saml.php", timeout=5)
    assert log["goto"] == [f"{BASE}/saml.php"]
    assert log["headless"] is False, "Browser muss sichtbar sein"
    assert log["closed"] is True
    assert cookies == {"PHPSESSID": "browser-session", "ilClientId": "ILIAS"}


def test_post_login_url_predicate():
    assert not browser_module.is_post_login_url(f"{BASE}/saml.php", BASE)
    assert not browser_module.is_post_login_url(f"{BASE}/login.php?cmd=force_login", BASE)
    assert not browser_module.is_post_login_url(f"{IDP}/idp/ilias.php", BASE)
    assert not browser_module.is_post_login_url(
        f"{BASE}/ilias.php?baseClass=ilStartUpGUI&cmd=showLogin", BASE
    )
    assert browser_module.is_post_login_url(f"{BASE}/ilias.php?baseClass=ilDashboardGUI", BASE)
    assert browser_module.is_post_login_url(f"{BASE}/goto.php/crs/123", BASE)


def test_browser_timeout_is_auth_error(monkeypatch):
    install_fake_playwright(monkeypatch, SAML_NAVIGATION[:2], COOKIES)
    with pytest.raises(AuthenticationError):
        browser_module.login_with_browser(BASE, start_path="saml.php", timeout=1)


def test_client_browser_login_verifies_and_stores(monkeypatch, mannheim_like):
    install_fake_playwright(monkeypatch, SAML_NAVIGATION, COOKIES)
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DASHBOARD).mock(return_value=html_response("ilias_dashboard.html"))
        result = IliasClient(mannheim_like).login_with_browser(timeout=5)
    assert result.method == "browser" and result.instance == "uni-mannheim"
    sent = route.calls[0].request.headers["cookie"]
    assert "browser-session" in sent and "idp-secret" not in sent
    assert SessionStore(mannheim_like).load() == {"PHPSESSID": "browser-session", "ilClientId": "ILIAS"}


def test_client_browser_login_rejected_stores_nothing(monkeypatch, mannheim_like):
    install_fake_playwright(monkeypatch, SAML_NAVIGATION, COOKIES)
    with respx.mock(assert_all_called=False) as router:
        router.get(DASHBOARD).mock(
            return_value=httpx.Response(302, headers={"location": f"{BASE}/login.php?cmd=force_login"})
        )
        router.get(f"{BASE}/login.php?cmd=force_login").mock(return_value=html_response("ilias_login.php"))
        with pytest.raises(AuthenticationError):
            IliasClient(mannheim_like).login_with_browser(timeout=5)
    assert SessionStore(mannheim_like).load() is None


def test_cli_browser_with_instance(monkeypatch, mannheim_like):
    log = install_fake_playwright(monkeypatch, SAML_NAVIGATION, COOKIES)
    with respx.mock(assert_all_called=True) as router:
        router.get(DASHBOARD).mock(return_value=html_response("ilias_dashboard.html"))
        result = CliRunner().invoke(app, ["login", "--instance", "uni-mannheim", "--browser", "--json"])
    assert result.exit_code == 0, result.output
    assert '"method": "browser"' in result.stdout
    assert "browser-session" not in result.output
    assert log["goto"] == [f"{BASE}/saml.php"]


def test_missing_playwright_gives_install_hint(monkeypatch, mannheim_like):
    monkeypatch.setitem(sys.modules, "playwright", None)
    result = CliRunner().invoke(app, ["login", "--instance", "uni-mannheim", "--browser"])
    assert result.exit_code == 1
    assert "uv sync --extra browser" in result.output
    assert "playwright install chromium" in result.output
