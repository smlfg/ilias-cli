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


# ---------------------------------------------------------------- Item 1: Byte-Obergrenzen (SEC-25)
from ilias_core.errors import SizeLimitError  # noqa: E402
from ilias_core.ilias_html.fetch import download_limit  # noqa: E402

PAGE = "/ilias.php?baseClass=ilDashboardGUI"


def test_page_over_cap_aborts_exit5(ilias, monkeypatch):
    monkeypatch.setenv("ILIAS_CLI_MAX_PAGE_BYTES", "1000")
    ilias.routes[PAGE] = (200, {"Content-Type": "text/html"}, LOGGED_IN_HTML.encode() + b"x" * 2000)
    fetcher = _fetcher(ilias, monkeypatch)
    with pytest.raises(SizeLimitError) as excinfo:
        fetcher.get(PAGE)
    assert excinfo.value.exit_code == 5 and excinfo.value.code == "size_limit"


def test_page_over_cap_without_content_length(ilias, monkeypatch):
    """Ohne Content-Length (chunked/close) greift die Grenze beim Lesen."""
    monkeypatch.setenv("ILIAS_CLI_MAX_PAGE_BYTES", "1000")
    ilias.routes[PAGE] = (
        200,
        {"Content-Type": "text/html", "Content-Length": "", "Connection": "close"},
        LOGGED_IN_HTML.encode() + b"y" * 5000,
    )
    fetcher = _fetcher(ilias, monkeypatch)
    with pytest.raises((SizeLimitError,)):
        fetcher.get(PAGE)


def test_page_under_cap_ok(ilias, monkeypatch):
    monkeypatch.setenv("ILIAS_CLI_MAX_PAGE_BYTES", "100000")
    ilias.routes[PAGE] = (200, {"Content-Type": "text/html"}, LOGGED_IN_HTML.encode())
    assert "Abmelden" in _fetcher(ilias, monkeypatch).get(PAGE).html


def test_download_limit_math():
    assert download_limit(None, 500) == 500
    assert download_limit(1000, 10**9) == 1500 + 1024 * 1024
    assert download_limit(10**9, 5000) == 5000


def _file_route(server: MiniServer, size: int, *, length: bool = True) -> str:
    headers = {"Content-Type": "application/pdf"}
    if not length:
        headers["Content-Length"] = ""
        headers["Connection"] = "close"
    server.routes["/datei"] = (200, headers, b"A" * size)
    return "/datei"


def test_download_over_hard_cap_deletes_part(ilias, monkeypatch, tmp_path):
    monkeypatch.setenv("ILIAS_CLI_MAX_DOWNLOAD_BYTES", "4096")
    path = _file_route(ilias, 10_000, length=False)
    dest = tmp_path / "kurs" / "x.pdf"
    with pytest.raises(SizeLimitError) as excinfo:
        _fetcher(ilias, monkeypatch).download(path, dest)
    assert excinfo.value.exit_code == 5
    assert not dest.exists() and not dest.with_name("x.pdf.part").exists()


def test_download_declared_length_over_cap_no_write(ilias, monkeypatch, tmp_path):
    monkeypatch.setenv("ILIAS_CLI_MAX_DOWNLOAD_BYTES", "4096")
    path = _file_route(ilias, 10_000)
    dest = tmp_path / "x.pdf"
    with pytest.raises(SizeLimitError):
        _fetcher(ilias, monkeypatch).download(path, dest)
    assert list(tmp_path.iterdir()) == []


def test_download_exceeds_listed_size_margin(ilias, monkeypatch, tmp_path):
    size = 3 * 1024 * 1024
    path = _file_route(ilias, size, length=False)
    dest = tmp_path / "x.pdf"
    with pytest.raises(SizeLimitError):
        _fetcher(ilias, monkeypatch).download(path, dest, expected_size=1000)
    assert not dest.exists() and not dest.with_name("x.pdf.part").exists()


def test_download_within_listed_size_ok(ilias, monkeypatch, tmp_path):
    path = _file_route(ilias, 5000)
    got = _fetcher(ilias, monkeypatch).download(path, tmp_path / "x.pdf", expected_size=4000)
    assert got.size == 5000 and (tmp_path / "x.pdf").read_bytes() == b"A" * 5000


# ---------------------------------------------------------------- Item 3: keine Symlinks (SEC-16)
from ilias_core import download as dl  # noqa: E402
from ilias_core.errors import UnsafePathError  # noqa: E402


def _victim(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("unverändert", encoding="utf-8")
    return victim


def test_download_refuses_symlinked_part(ilias, monkeypatch, tmp_path):
    victim = _victim(tmp_path)
    path = _file_route(ilias, 100)
    dest = tmp_path / "kurs" / "x.pdf"
    dest.parent.mkdir()
    dest.with_name("x.pdf.part").symlink_to(victim)
    with pytest.raises(UnsafePathError) as excinfo:
        _fetcher(ilias, monkeypatch).download(path, dest)
    assert excinfo.value.exit_code == 1
    assert victim.read_text(encoding="utf-8") == "unverändert" and not dest.exists()


def test_download_refuses_symlinked_dest(ilias, monkeypatch, tmp_path):
    victim = _victim(tmp_path)
    path = _file_route(ilias, 100)
    dest = tmp_path / "x.pdf"
    dest.symlink_to(victim)
    with pytest.raises(UnsafePathError):
        _fetcher(ilias, monkeypatch).download(path, dest)
    assert victim.read_text(encoding="utf-8") == "unverändert" and dest.is_symlink()


def test_download_replaces_stale_regular_part(ilias, monkeypatch, tmp_path):
    path = _file_route(ilias, 100)
    dest = tmp_path / "x.pdf"
    dest.with_name("x.pdf.part").write_bytes(b"alt")
    _fetcher(ilias, monkeypatch).download(path, dest)
    assert dest.read_bytes() == b"A" * 100 and not dest.with_name("x.pdf.part").exists()


def test_save_manifest_refuses_symlinked_part(tmp_path):
    victim = _victim(tmp_path)
    course = tmp_path / "kurs"
    course.mkdir()
    (course / (dl.MANIFEST_NAME + ".part")).symlink_to(victim)
    with pytest.raises(UnsafePathError):
        dl.save_manifest(course, {"1": {"relpath": "a.pdf"}})
    assert victim.read_text(encoding="utf-8") == "unverändert"


def test_manifest_symlink_ignored_and_refused(tmp_path):
    victim = _victim(tmp_path)
    course = tmp_path / "kurs"
    course.mkdir()
    (course / dl.MANIFEST_NAME).symlink_to(victim)
    assert dl.load_manifest(course) == {}
    with pytest.raises(UnsafePathError):
        dl.save_manifest(course, {})
    assert victim.read_text(encoding="utf-8") == "unverändert"


def test_save_manifest_normal(tmp_path):
    course = tmp_path / "kurs"
    dl.save_manifest(course, {"1": {"relpath": "a.pdf"}})
    assert dl.load_manifest(course) == {"1": {"relpath": "a.pdf"}}
    assert not (course / (dl.MANIFEST_NAME + ".part")).exists()


def test_refuse_symlinks_in_course_chain(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "kurs").symlink_to(real, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        dl.refuse_symlinks(tmp_path / "kurs", tmp_path / "kurs" / "a" / "b.pdf")
    dl.refuse_symlinks(real, real / "fehlt" / "b.pdf")  # nicht vorhandene Segmente sind ok
