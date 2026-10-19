"""`ilias status` folgt keinen Weiterleitungen zum IdP (Issue #51).

Gleiche Regeln wie ``ilias_core.ilias_html.fetch`` (``follow_redirects=False``,
``is_auth_redirect``): Redirect auf Keycloak, ``openidconnect.php`` oder fremden Host
-> Exit 3 nach genau einem ILIAS-Request, kein IdP-Kontakt.
"""

from __future__ import annotations

import urllib.parse

from .conftest import HhnHarness


def _patch_dashboard_to_keycloak(h: HhnHarness, monkeypatch) -> None:
    def to_keycloak(handler, target: str = "") -> None:
        handler._redirect(
            f"{h.world.kc_base}/realms/hhn/protocol/openid-connect/auth?client_id=x&state={urllib.parse.quote(target)}"
        )

    monkeypatch.setattr(h.world, "_login_redirect", to_keycloak)


def test_status_redirect_to_keycloak_exit_3_single_request(logged_in: HhnHarness, monkeypatch):
    logged_in.world.expire_all_sessions()
    _patch_dashboard_to_keycloak(logged_in, monkeypatch)
    n_before = len(logged_in.world.requests)
    r = logged_in.run("status")
    assert r.exit_code == 3, str(r)
    after = logged_in.world.requests[n_before:]
    assert len([x for x in after if x.server == "ilias"]) == 1
    assert not any(x.server == "keycloak" for x in after)


def test_status_redirect_to_openidconnect_exit_3_no_follow(logged_in: HhnHarness, monkeypatch):
    logged_in.world.expire_all_sessions()

    def to_oidc(handler, target: str = "") -> None:
        handler._redirect(f"{logged_in.world.ilias_base}/openidconnect.php")

    monkeypatch.setattr(logged_in.world, "_login_redirect", to_oidc)
    n_before = len(logged_in.world.requests)
    r = logged_in.run("status")
    assert r.exit_code == 3, str(r)
    after = logged_in.world.requests[n_before:]
    assert len([x for x in after if x.server == "ilias"]) == 1
    assert not any("openidconnect" in x.path for x in after if x.server == "ilias" and x != after[0])
    assert not any(x.server == "keycloak" for x in after)
