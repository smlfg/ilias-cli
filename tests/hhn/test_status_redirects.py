"""#51: `ilias status` folgt keinen Weiterleitungen in den Login-/IdP-Fluss.

Abgelaufene Session: ILIAS leitet das Dashboard um. Erwartet: Exit 3 `session_expired` nach
genau **einem** ILIAS-Request, Keycloak (anderer Host/Port) bekommt null Requests.
Nur Fake-Server auf localhost.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_status_redirects.py -q`
"""

from __future__ import annotations

import pytest

from .conftest import HhnHarness
from .helpers import err_json, ok_json


def _requests(h: HhnHarness, since: int, server: str) -> list:
    return [r for r in h.world.requests[since:] if r.server == server]


def test_status_ok_one_request(logged_in: HhnHarness):
    h = logged_in
    since = len(h.world.requests)
    ok_json(h.run("status", "--json"))
    assert len(_requests(h, since, "ilias")) == 1
    assert _requests(h, since, "keycloak") == []


@pytest.mark.parametrize("target", ["login_php", "keycloak"])
def test_status_expired_does_not_follow_idp_redirect(logged_in: HhnHarness, target: str):
    h = logged_in
    world = h.world
    if target == "keycloak":
        world._login_redirect = lambda handler, _t="": handler._redirect(  # type: ignore[method-assign]
            f"{world.kc_base}/realms/hhn/protocol/openid-connect/auth?client_id=x&response_type=code"
        )
    world.expire_all_sessions()
    since = len(world.requests)
    err_json(h.run("status", "--json"), 3, "session_expired")
    assert len(_requests(h, since, "ilias")) == 1, [r.path for r in world.requests[since:]]
    assert _requests(h, since, "keycloak") == []
    assert all(r.method == "GET" for r in world.requests[since:])


def test_status_follows_same_host_redirect(logged_in: HhnHarness):
    """Eine Weiterleitung innerhalb von ILIAS (z. B. Dashboard-Unterseite) bleibt erlaubt."""
    h = logged_in
    world = h.world
    original = world.handle_repo

    def handle(handler, rec):
        if rec.path == "/ilias.php" and rec.query.get("baseClass", [""])[0] == "ilDashboardGUI" \
                and "cmd" not in rec.query:
            handler._redirect(f"{world.ilias_base}/ilias.php?baseClass=ilDashboardGUI&cmd=show")
            return True
        return original(handler, rec)

    world.handle_repo = handle  # type: ignore[method-assign]
    since = len(world.requests)
    ok_json(h.run("status", "--json"))
    assert len(_requests(h, since, "ilias")) == 2
