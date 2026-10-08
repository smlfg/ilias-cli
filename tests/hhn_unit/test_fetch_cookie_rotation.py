"""Cookie-Rotation im ILIAS-GET-Helfer (``ilias_core.ilias_html.fetch.Fetcher``).

Portiert aus der früheren zweiten HTTP-Schicht (``ilias_core.web``, PR #23): setzt ILIAS
per ``Set-Cookie`` ein neues ``PHPSESSID``/``ilClientId``, wird der neue Wert gespeichert
(Spec §4.4, L2). Nie Keycloak-/Fremd-Cookies, nie nach einer abgelaufenen Session.
Kein Netzwerk: ``httpx.MockTransport``, nur synthetische Werte.
"""

from __future__ import annotations

import httpx
import pytest

from ilias_core.config import Config
from ilias_core.errors import PermissionDeniedError, SessionExpiredError
from ilias_core.ilias_html.fetch import Fetcher

BASE = "https://ilias.example.org"
OK_HTML = "<html><body><div id='il_center_col'>ok</div><a href='logout.php'>x</a></body></html>"
DENIED_HTML = "<html><body><div class='alert-danger'>Keine Berechtigung</div></body></html>"


class _Store:
    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = dict(cookies)
        self.saved: list[dict[str, str]] = []

    def load(self):
        return dict(self.cookies)

    def save(self, cookies: dict[str, str]) -> None:
        self.cookies = dict(cookies)
        self.saved.append(dict(cookies))


def _fetcher(monkeypatch, handler, store: _Store) -> Fetcher:
    monkeypatch.setenv("ILIAS_CLI_REQUEST_INTERVAL", "0")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return Fetcher(Config(base_url=BASE, instance="hhn"), store, client=client)


def _start_store() -> _Store:
    return _Store({"PHPSESSID": "sess-old-0001", "ilClientId": "hhn", "other": "keep-me"})


def test_rotated_phpsessid_is_saved_and_others_kept(monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(
            200,
            html=OK_HTML,
            headers=[("set-cookie", "PHPSESSID=sess-new-0002; Path=/; HttpOnly")],
        )

    store = _start_store()
    fetcher = _fetcher(monkeypatch, handler, store)
    fetcher.get("/ilias.php?baseClass=ilmembershipoverviewgui")
    assert store.saved == [{"PHPSESSID": "sess-new-0002", "ilClientId": "hhn", "other": "keep-me"}]
    # der nächste Request schickt schon den neuen Wert, gespeichert wird nicht erneut
    fetcher.get("/ilias.php?baseClass=ilmembershipoverviewgui")
    assert "sess-new-0002" in (seen[-1] or "")
    assert len(store.saved) == 1


def test_no_save_without_rotation(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        # ILIAS setzt pro Seite ilClientId mit gleichem Wert neu (Spec §13.10): keine Änderung
        return httpx.Response(200, html=OK_HTML, headers=[("set-cookie", "ilClientId=hhn; Path=/")])

    store = _start_store()
    _fetcher(monkeypatch, handler, store).get("/ilias.php?baseClass=ilmembershipoverviewgui")
    assert store.saved == []


def test_rotation_never_stores_keycloak_or_unlisted_cookies(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            html=OK_HTML,
            headers=[
                ("set-cookie", "KEYCLOAK_IDENTITY=kc-secret; Path=/"),
                ("set-cookie", "AUTH_SESSION_ID=kc-auth; Path=/"),
                ("set-cookie", "tracking=xyz; Path=/"),
                ("set-cookie", "ilClientId=hhn2; Path=/"),
            ],
        )

    store = _start_store()
    _fetcher(monkeypatch, handler, store).get("/ilias.php?baseClass=ilmembershipoverviewgui")
    assert store.saved == [{"PHPSESSID": "sess-old-0001", "ilClientId": "hhn2", "other": "keep-me"}]


def test_rotation_across_same_host_redirect(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go/crs/900101":
            return httpx.Response(
                302,
                headers=[
                    ("location", f"{BASE}/ilias.php?baseClass=ilrepositorygui&ref_id=900101"),
                    ("set-cookie", "PHPSESSID=sess-redirect-0003; Path=/"),
                ],
            )
        return httpx.Response(200, html=OK_HTML)

    store = _start_store()
    fetcher = _fetcher(monkeypatch, handler, store)
    fetcher.get("/go/crs/900101", expect_ref=900101)
    assert fetcher.request_count == 2
    assert store.saved and store.saved[-1]["PHPSESSID"] == "sess-redirect-0003"


def test_no_save_when_session_expired(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers=[
                ("location", f"{BASE}/login.php?cmd=force_login"),
                ("set-cookie", "PHPSESSID=anonymous-0004; Path=/"),
            ],
        )

    store = _start_store()
    fetcher = _fetcher(monkeypatch, handler, store)
    with pytest.raises(SessionExpiredError):
        fetcher.get("/ilias.php?baseClass=ilmembershipoverviewgui")
    assert fetcher.request_count == 1
    assert store.saved == []


def test_rotation_saved_on_permission_denied(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=DENIED_HTML, headers=[("set-cookie", "PHPSESSID=sess-new-0005; Path=/")])

    store = _start_store()
    with pytest.raises(PermissionDeniedError):
        _fetcher(monkeypatch, handler, store).get("/ilias.php?baseClass=ilrepositorygui&ref_id=1")
    assert store.saved and store.saved[-1]["PHPSESSID"] == "sess-new-0005"
