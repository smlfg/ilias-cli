"""SAML/Shibboleth-Login (Uni Mannheim) und Instanz-Profile, gegen lokale Fakes.

Gleiche Harness wie die Akzeptanztests (Subprozess, Netzwerk-Sandbox, Fake-Keyring).
Die Fake-Seiten basieren auf den echten Seiten in tests/fixtures/uni-mannheim/.
"""

from __future__ import annotations

import os
import sys

import pytest

from .conftest import PASSWORD, TOTP, USERNAME, Harness, assert_no_external_network, file_mode
from .fake_servers import FakeWorld
from .fake_shibboleth import ACS_PATH, CONSENT_DEFAULT, SSO_PATH, WRONG_PASSWORD_MESSAGE, FakeShibWorld
from .leak_check import find_secret_in_paths, find_secret_in_text

AUTH_FAIL_CODES = {1, 2}
INSTANCE = ("--instance", "uni-mannheim")


@pytest.fixture
def saml_world():
    w = FakeShibWorld(username=USERNAME, password=PASSWORD).start()
    yield w
    w.stop()


@pytest.fixture
def sh(tmp_path, saml_world) -> Harness:
    harness = Harness(tmp_path, saml_world)
    write_instance_config(harness)
    yield harness
    assert_no_external_network(harness)


def write_instance_config(h: Harness, *, top_level: bool = False) -> None:
    if top_level:
        text = f'instance = "uni-mannheim"\nbase_url = "{h.world.ilias_base}"\n'
    else:
        text = f'[instances.uni-mannheim]\nbase_url = "{h.world.ilias_base}"\n'
    (h.config_dir / "config.toml").write_text(text, encoding="utf-8")


def saml_login(h: Harness, *extra: str, password: str = PASSWORD) -> object:
    return h.run("login", *INSTANCE, *extra, input=f"{USERNAME}\n{password}\n")


def idp_posts(h: Harness):
    return [r for r in h.world.requests_to("idp") if r.method == "POST"]


def acs_posts(h: Harness):
    return [r for r in h.world.requests_to("ilias") if r.method == "POST" and r.path == ACS_PATH]


def assert_nothing_stored(h: Harness) -> None:
    assert h.session_artifacts() == [], f"Session trotz Fehler gespeichert: {h.session_artifacts()}"
    s = h.run("status", *INSTANCE)
    assert s.exit_code == 2, str(s)


# ---------------------------------------------------------------- Erfolg
def test_saml_login_success_and_status(sh: Harness):
    r = saml_login(sh)
    assert r.exit_code == 0, str(r)
    assert "TOTP" not in r.stdout + r.stderr, "SAML-Flow darf keinen TOTP-Code abfragen"

    ilias = sh.world.requests_to("ilias")
    assert ilias[0].method == "GET" and ilias[0].path == "/saml.php", "Start bei saml.php fehlt"
    posts = idp_posts(sh)
    assert len(posts) == 1, f"erwartet 1 POST an den IdP, bekommen {len(posts)}"
    form = posts[0].form
    assert posts[0].path == SSO_PATH and posts[0].query.get("execution") == ["e1s1"]
    assert form.get("j_username") == [USERNAME]
    assert "j_password" in form
    assert form.get("csrf_token", [""])[0].startswith("_"), "csrf_token nicht mitgesendet"
    assert "_eventId_proceed" in form
    assert "donotcache" not in form and "_shib_idp_revokeConsent" not in form, "nicht angehakte Checkboxen gesendet"

    acs = acs_posts(sh)
    assert len(acs) == 1 and acs[0].form.get("SAMLResponse") and acs[0].form.get("RelayState")
    assert any(r.path == "/ilias.php" and r.query.get("baseClass") == ["ilDashboardGUI"] for r in ilias[ilias.index(acs[0]):])

    s = sh.run("status", *INSTANCE, "--json")
    assert s.exit_code == 0, str(s)
    data = s.json()
    assert data["authenticated"] is True and data["instance"] == "uni-mannheim"


def test_saml_login_json(sh: Harness):
    r = saml_login(sh, "--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert data["method"] == "saml-shibboleth" and data["instance"] == "uni-mannheim"
    for sid in sh.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr


def test_saml_instance_from_config_key(sh: Harness):
    """`instance = "uni-mannheim"` in config.toml statt --instance; base_url bleibt überschreibbar (N7)."""
    write_instance_config(sh, top_level=True)
    r = sh.run("login", input=f"{USERNAME}\n{PASSWORD}\n")
    assert r.exit_code == 0, str(r)
    assert sh.run("status").exit_code == 0


def test_saml_consent_page(sh: Harness):
    sh.world.consent = True
    r = saml_login(sh)
    assert r.exit_code == 0, str(r)
    posts = idp_posts(sh)
    assert len(posts) == 2, [p.query for p in posts]
    consent = posts[1].form
    assert "_eventId_proceed" in consent
    assert consent.get("_shib_idp_consentOptions") == [CONSENT_DEFAULT], "Default-Consent-Option nicht beibehalten"
    assert "_eventId_AttributeReleaseRejected" not in consent
    assert len(acs_posts(sh)) == 1


def test_saml_consent_and_client_storage_pages(sh: Harness):
    sh.world.consent = True
    sh.world.client_storage = True
    r = saml_login(sh)
    assert r.exit_code == 0, str(r)
    assert len(idp_posts(sh)) == 3
    assert sh.run("status", *INSTANCE).exit_code == 0


def test_saml_user_agent(sh: Harness):
    assert saml_login(sh).exit_code == 0
    uas = {r.headers.get("User-Agent", "") for r in sh.world.requests}
    assert uas and all(ua.startswith("ilias-cli/") for ua in uas), uas


def test_saml_only_ilias_cookies_stored(sh: Harness):
    assert saml_login(sh).exit_code == 0
    artifacts = sh.session_artifacts()
    assert artifacts, "Session-Cookie wurde nirgends gespeichert"
    for p in artifacts:
        assert sh.cwd not in p.parents
        if p != sh.keyring_file and os.name != "nt":
            assert file_mode(p) == 0o600
    for name in ("JSESSIONID", "shib_idp_session"):
        assert sh.files_containing(name) == [], f"IdP-Cookie {name} gespeichert"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Rechte")
def test_saml_file_fallback_without_keyring(sh: Harness):
    sh.keyring_mode = "none"
    assert saml_login(sh).exit_code == 0
    files = [p for p in sh.session_artifacts() if p != sh.keyring_file]
    assert files and all(file_mode(p) == 0o600 for p in files)
    assert sh.run("status", *INSTANCE).exit_code == 0


# ---------------------------------------------------------------- Fehler
def test_saml_wrong_password(sh: Harness):
    r = saml_login(sh, password="falsches-Passwort-123")
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert WRONG_PASSWORD_MESSAGE in r.stderr, "Fehlermeldung des IdP nicht angezeigt"
    assert acs_posts(sh) == []
    assert len(idp_posts(sh)) == 1, "Login nach falschem Passwort wiederholt"
    assert_nothing_stored(sh)


def test_saml_unexpected_idp_html_exit_5(sh: Harness):
    sh.world.idp_entry_mode = "garbage"
    r = saml_login(sh)
    assert r.exit_code == 5, str(r)
    assert idp_posts(sh) == [], "Passwort an unbekannte Seite gesendet"
    assert_nothing_stored(sh)


def test_saml_unexpected_html_after_login_exit_5(sh: Harness):
    sh.world.idp_post_mode = "garbage"
    r = saml_login(sh)
    assert r.exit_code == 5, str(r)
    assert_nothing_stored(sh)


def test_saml_server_error_exit_4(sh: Harness):
    sh.world.idp_post_mode = "error502"
    r = saml_login(sh)
    assert r.exit_code == 4, str(r)
    assert_nothing_stored(sh)


def test_saml_ilias_rejects_assertion_nothing_stored(sh: Harness):
    """Verifikation: SAML-Antwort gesendet, aber ILIAS stellt keine Session aus -> kein Erfolg."""
    sh.world.acs_mode = "no_session"
    r = saml_login(sh)
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert "erfolgreich" not in r.stdout
    assert_nothing_stored(sh)


def test_saml_dashboard_without_logged_in_marker_exit_5(sh: Harness):
    sh.world.dashboard_mode = "no_marker"
    r = saml_login(sh)
    assert r.exit_code == 5, str(r)
    assert_nothing_stored(sh)


def test_saml_status_expired_exit_3_without_relogin(sh: Harness):
    assert saml_login(sh).exit_code == 0
    sh.world.expire_all_sessions()
    n_before = len(sh.world.requests)
    r = sh.run("status", *INSTANCE)
    assert r.exit_code == 3, str(r)
    after = sh.world.requests[n_before:]
    assert not any(x.server == "idp" or x.path == "/saml.php" for x in after), "Re-Login versucht (A5)"


def test_saml_status_without_marker_exit_5(sh: Harness):
    assert saml_login(sh).exit_code == 0
    sh.world.dashboard_mode = "no_marker"
    assert sh.run("status", *INSTANCE).exit_code == 5


# ---------------------------------------------------------------- --debug
@pytest.mark.parametrize("password", [PASSWORD, "falsches-Passwort-123"])
def test_saml_debug_output_is_safe(sh: Harness, password: str):
    """--debug: URLs, Statuscodes, Feldnamen; nie Werte, Passwort, Cookies, Tokens."""
    sh.world.consent = True
    r = saml_login(sh, "--debug", password=password)
    log = r.stderr
    assert "[debug]" in log
    for expected in ("/saml.php", SSO_PATH, "302", "j_username", "j_password", "csrf_token", "_eventId_proceed"):
        assert expected in log, f"{expected!r} fehlt im Debug-Log:\n{log}"
    if password == PASSWORD:
        assert r.exit_code == 0, str(r)
        for expected in ("SAMLResponse", "RelayState", "_shib_idp_consentOptions", ACS_PATH):
            assert expected in log, f"{expected!r} fehlt im Debug-Log:\n{log}"
    secrets_ = [password, USERNAME, *sh.world.issued_secrets, *sh.world.issued_session_ids]
    for secret in secrets_:
        assert not find_secret_in_text(secret, r.stdout + r.stderr), f"Wert im Debug-Log: {secret[:6]}…"
    assert "Set-Cookie" not in log and "SAMLRequest=" + "P" not in log


def test_debug_status_is_safe(sh: Harness):
    assert saml_login(sh).exit_code == 0
    r = sh.run("status", *INSTANCE, "--debug")
    assert r.exit_code == 0, str(r)
    assert "ilDashboardGUI" in r.stderr
    for sid in sh.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr


# ---------------------------------------------------------------- A1
SAML_LEAK_SCENARIOS = ["success", "wrong_password", "garbage_html", "after_login_garbage", "rejected", "debug"]


@pytest.mark.parametrize("scenario", SAML_LEAK_SCENARIOS)
def test_saml_password_never_in_output_or_files(sh: Harness, scenario: str):
    password = PASSWORD
    extra: tuple[str, ...] = ()
    if scenario == "wrong_password":
        password = PASSWORD + "-x"
    elif scenario == "garbage_html":
        sh.world.idp_entry_mode = "garbage"
    elif scenario == "after_login_garbage":
        sh.world.idp_post_mode = "garbage"
    elif scenario == "rejected":
        sh.world.acs_mode = "no_session"
    elif scenario == "debug":
        extra = ("--debug",)
    saml_login(sh, *extra, password=password)
    sh.run("status", *INSTANCE, *extra)
    assert not find_secret_in_text(password, sh.all_output()), "Passwort in Ausgabe!\n" + sh.all_output()
    hits = find_secret_in_paths(password, [sh.home, sh.config_dir, sh.cwd, sh.keyring_file.parent])
    assert hits == [], f"Passwort in Dateien: {hits}"


# ---------------------------------------------------------------- Instanzen
def test_sessions_are_per_instance(tmp_path, saml_world):
    """HHN (OIDC+TOTP) und Uni Mannheim (SAML) nebeneinander; Logout betrifft nur eine Instanz."""
    oidc = FakeWorld(username=USERNAME, password=PASSWORD, totp=TOTP).start()
    try:
        h = Harness(tmp_path, saml_world)
        (h.config_dir / "config.toml").write_text(
            f'[instances.hhn]\nbase_url = "{oidc.ilias_base}"\n'
            f'[instances.uni-mannheim]\nbase_url = "{saml_world.ilias_base}"\n',
            encoding="utf-8",
        )
        r = h.run("login", "--instance", "hhn", input=f"{USERNAME}\n{PASSWORD}\n{TOTP}\n")
        assert r.exit_code == 0, str(r)
        assert saml_login(h).exit_code == 0
        assert h.run("status").exit_code == 0, "Default-Instanz hhn"
        assert h.run("status", *INSTANCE).exit_code == 0

        out = h.run("logout", *INSTANCE, "--json")
        assert out.exit_code == 0 and out.json()["instance"] == "uni-mannheim", str(out)
        assert h.run("status", *INSTANCE).exit_code == 2
        assert h.run("status", "--instance", "hhn").exit_code == 0
    finally:
        oidc.stop()
    assert_no_external_network(h)


def test_unknown_instance_fails_cleanly(sh: Harness):
    r = sh.run("status", "--instance", "gibt-es-nicht", "--json")
    assert r.exit_code == 1, str(r)
    data = r.json()
    assert data["ok"] is False and "uni-mannheim" in data["message"]


def test_help_mentions_instance_debug_browser(sh: Harness):
    r = sh.run("login", "--help")
    for option in ("--instance", "--debug", "--browser"):
        assert option in r.stdout, r.stdout
    for cmd in ("status", "logout"):
        out = sh.run(cmd, "--help").stdout
        assert "--instance" in out and "--debug" in out
