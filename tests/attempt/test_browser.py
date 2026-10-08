from __future__ import annotations

import sys
import types

import pytest

from ilias_core import browser_auth
from ilias_core.models import SessionData


def test_browser_login_with_mocked_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def goto(self, url: str) -> None:
            self.url = url

        def wait_for_url(self, pattern: str, timeout: int) -> None:
            return None

    class FakeContext:
        def new_page(self) -> FakePage:
            return FakePage()

        def cookies(self):
            return [{"name": "PHPSESSID", "value": "browsersession"}, {"name": "ilClientId", "value": "iliashhn"}]

    class FakeBrowser:
        def new_context(self) -> FakeContext:
            return FakeContext()

        def close(self) -> None:
            pass

    class FakeChromium:
        def launch(self, headless: bool) -> FakeBrowser:
            assert headless is False
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_sync_api = types.ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakePlaywright()  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.sync_api = fake_sync_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    data = browser_auth.login_with_browser("https://ilias.hs-heilbronn.de")
    assert isinstance(data, SessionData)
    assert data.cookies["PHPSESSID"] == "browsersession"


def test_browser_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    from ilias_core.errors import BrowserUnavailableError

    with pytest.raises(BrowserUnavailableError) as ei:
        browser_auth.login_with_browser("https://ilias.hs-heilbronn.de")
    assert ei.value.exit_code == 1
