"""Login gilt erst nach Verifikation als erfolgreich (HHN-Flow, OIDC + TOTP).

Erfolg nur, wenn die Redirect-Kette zu ILIAS zurückkehrt, das Session-Cookie neu ist
und das Dashboard nicht auf login.php umleitet und ein Login-Merkmal zeigt.
Sonst: Fehler-Exit-Code und nichts gespeichert. `status` prüft dasselbe Dashboard.
"""

from __future__ import annotations

from .conftest import Harness

AUTH_FAIL_CODES = {1, 2}


def assert_nothing_stored(h: Harness) -> None:
    assert h.session_artifacts() == [], f"Session trotz Fehler gespeichert: {h.session_artifacts()}"
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_success_requires_dashboard_check(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    ilias = h.world.requests_to("ilias")
    callback = next(i for i, x in enumerate(ilias) if x.path.endswith("/openidconnect.php") and "code" in x.query)
    assert any(x.path.endswith("/ilias.php") and x.query.get("baseClass") == ["ilDashboardGUI"] for x in ilias[callback:])


def test_session_cookie_not_renewed_is_failure(h: Harness):
    h.world.callback_mode = "no_new_session"
    r = h.login()
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert "erfolgreich" not in r.stdout
    assert_nothing_stored(h)


def test_new_cookie_but_dashboard_redirects_to_login_is_failure(h: Harness):
    h.world.callback_mode = "session_not_valid"
    r = h.login()
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert_nothing_stored(h)


def test_dashboard_without_marker_is_parser_error(h: Harness):
    h.world.dashboard_mode = "no_marker"
    r = h.login()
    assert r.exit_code == 5, str(r)
    assert_nothing_stored(h)


def test_dashboard_shows_login_page_inline_is_failure(h: Harness):
    h.world.dashboard_mode = "login_inline"
    r = h.login()
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert_nothing_stored(h)


def test_status_without_marker_exit_5(h: Harness):
    assert h.login().exit_code == 0
    h.world.dashboard_mode = "no_marker"
    r = h.run("status", "--json")
    assert r.exit_code == 5, str(r)
    assert r.json()["ok"] is False


def test_status_login_page_inline_exit_3(h: Harness):
    assert h.login().exit_code == 0
    h.world.dashboard_mode = "login_inline"
    assert h.run("status").exit_code == 3


def test_hhn_debug_output_is_safe(h: Harness):
    from .conftest import PASSWORD, TOTP, USERNAME
    from .leak_check import find_secret_in_text

    r = h.login("--debug")
    assert r.exit_code == 0, str(r)
    for expected in ("openidconnect.php", "username", "password", "otp", "kc_acceptance_nonce", "code=…"):
        assert expected in r.stderr, f"{expected!r} fehlt im Debug-Log:\n{r.stderr}"
    for secret in (PASSWORD, TOTP, USERNAME, *h.world.issued_session_ids, *h.world.codes):
        assert not find_secret_in_text(secret, r.stdout + r.stderr)
