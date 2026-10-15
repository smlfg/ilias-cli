"""SEC-16/18/25-Härtung des ILIAS-Fetchers: fremder Host, Byte-Obergrenzen.

Nur lokale Server (127.0.0.1), synthetische Daten.
"""

from __future__ import annotations

import pytest

from ilias_core.config import Config
from ilias_core.errors import ForeignHostError
from ilias_core.ilias_html.fetch import Fetcher, same_instance_origin

from ._mini_server import LOGGED_IN_HTML, MiniServer, Store


@pytest.fixture
def ilias():
    s = MiniServer().start()
    yield s
    s.stop()


@pytest.fixture
def foreign():
    s = MiniServer().start()
    yield s
    s.stop()


def _fetcher(server: MiniServer, monkeypatch) -> Fetcher:
    monkeypatch.setenv("ILIAS_CLI_REQUEST_INTERVAL", "0")
    return Fetcher(Config(base_url=server.base, instance="hhn"), Store())


# ---------------------------------------------------------------- Item 4: fremder Host
def test_same_instance_origin():
    base = "https://ilias.example.org"
    assert same_instance_origin("/ilias.php?ref_id=1", base)
    assert same_instance_origin("https://ILIAS.example.org:443/x", base)
    assert not same_instance_origin("http://ilias.example.org/x", base)  # anderes Schema
    assert not same_instance_origin("https://ilias.example.org:8443/x", base)
    assert not same_instance_origin("https://evil.example.net/x", base)


def test_get_foreign_absolute_url_no_request(ilias, foreign, monkeypatch):
    fetcher = _fetcher(ilias, monkeypatch)
    with pytest.raises(ForeignHostError) as excinfo:
        fetcher.get(f"{foreign.base}/ilias.php?baseClass=ilrepositorygui&ref_id=1")
    assert excinfo.value.exit_code == 5
    assert foreign.requests == [] and ilias.requests == []
    assert fetcher.request_count == 0


def test_download_foreign_absolute_url_no_request(ilias, foreign, monkeypatch, tmp_path):
    fetcher = _fetcher(ilias, monkeypatch)
    with pytest.raises(ForeignHostError):
        fetcher.download(f"{foreign.base}/datei.pdf", tmp_path / "x.pdf")
    assert foreign.requests == [] and ilias.requests == []
    assert not (tmp_path / "x.pdf").exists() and not (tmp_path / "x.pdf.part").exists()


def test_get_same_host_still_works(ilias, monkeypatch):
    ilias.routes["/ilias.php?baseClass=ilDashboardGUI"] = (200, {"Content-Type": "text/html"}, LOGGED_IN_HTML.encode())
    fetcher = _fetcher(ilias, monkeypatch)
    page = fetcher.get(f"{ilias.base}/ilias.php?baseClass=ilDashboardGUI")
    assert "Abmelden" in page.html and len(ilias.requests) == 1
