"""Harte Byte-Obergrenze pro GET im ``Fetcher`` (SEC-25 / Issue #50)."""

from __future__ import annotations

import pytest
from hhn.fake_hhn import HhnWorld

from ilias_core.config import Config
from ilias_core.errors import ResponseTooLargeError
from ilias_core.ilias_html.fetch import Fetcher


class _Store:
    def load(self):
        return {"PHPSESSID": "sess-valid-0001"}


@pytest.fixture
def world():
    w = HhnWorld(username="test.user", password="not-a-real-password", totp="000000").start()
    w.valid_sessions.add("sess-valid-0001")
    yield w
    w.stop()


def _fetcher(world: HhnWorld, monkeypatch, *, max_bytes: str) -> Fetcher:
    monkeypatch.setenv("ILIAS_CLI_REQUEST_INTERVAL", "0")
    monkeypatch.setenv("ILIAS_CLI_MAX_RESPONSE_BYTES", max_bytes)
    config = Config(base_url=world.ilias_base, instance="hhn")
    return Fetcher(config, _Store())


def test_get_aborts_on_oversized_membership_page(world, monkeypatch):
    """Übergroße HTML-Antwort vom Fake -> Exit 5 ``response_too_large``, kein Parser-Ergebnis."""

    world.membership_mode = "oversized"
    fetcher = _fetcher(world, monkeypatch, max_bytes="4096")
    with pytest.raises(ResponseTooLargeError) as excinfo:
        fetcher.get("/ilias.php?baseClass=ilmembershipoverviewgui", label="Mitgliedschaften")
    err = excinfo.value
    assert err.exit_code == 5
    assert err.code == "response_too_large"
    assert fetcher.request_count == 1
