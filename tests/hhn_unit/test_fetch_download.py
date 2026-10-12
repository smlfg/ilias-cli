"""Datei-Download: HTML mit Content-Disposition ist die Datei, keine ILIAS-Seite."""

from __future__ import annotations

import httpx
import pytest

from ilias_core.config import Config
from ilias_core.errors import ParserError, PermissionDeniedError
from ilias_core.ilias_html.fetch import Fetcher

BASE = "https://ilias.example.org"


class _Store:
    def load(self):
        return {"PHPSESSID": "session-0000"}


def _fetcher(monkeypatch, handler) -> Fetcher:
    monkeypatch.setenv("ILIAS_CLI_REQUEST_INTERVAL", "0")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return Fetcher(Config(base_url=BASE, instance="hhn"), _Store(), client=client)


def test_html_attachment_is_saved_even_if_body_looks_like_a_page(tmp_path, monkeypatch):
    body = b'<html><form id="login_form"></form><div class="alert-danger">nein</div></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=UTF-8",
                "Content-Disposition": "attachment; filename*=UTF-8''L%C3%B6sung.html",
            },
            content=body,
        )

    dest = tmp_path / "Lösungshinweise.html"
    got = _fetcher(monkeypatch, handler).download("/sendfile", dest)
    assert dest.read_bytes() == body
    assert got.size == len(body)
    assert got.content_type == "text/html"
    assert got.server_filename == "Lösung.html"
    assert not dest.with_name(dest.name + ".part").exists()


def test_inline_xhtml_with_filename_is_saved(tmp_path, monkeypatch):
    body = b"<html xmlns='http://www.w3.org/1999/xhtml'><body>Skript</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/xhtml+xml",
                "Content-Disposition": 'inline; filename="Skript.xhtml"',
            },
            content=body,
        )

    dest = tmp_path / "Skript.xhtml"
    got = _fetcher(monkeypatch, handler).download("/sendfile", dest)
    assert dest.read_bytes() == body
    assert got.server_filename == "Skript.xhtml"
    assert got.content_type == "application/xhtml+xml"


def test_html_page_without_disposition_stays_an_error(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=b'<html><div class="alert-danger">keine Berechtigung</div></html>',
        )

    with pytest.raises(PermissionDeniedError):
        _fetcher(monkeypatch, handler).download("/sendfile", tmp_path / "x.bin")


def test_plain_html_page_is_parse_error(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html><p>Infoseite statt Datei</p></html>",
        )

    with pytest.raises(ParserError):
        _fetcher(monkeypatch, handler).download("/sendfile", tmp_path / "x.bin")
