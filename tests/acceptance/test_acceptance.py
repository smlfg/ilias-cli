"""Akzeptanztests für F1 (login/status/logout) und A1–A6 aus ANFORDERUNGEN.md.

Jeder Test nennt die Anforderung(en), die er prüft. Schnittstelle: INTERFACE.md.
"""

from __future__ import annotations

import os
import sys

import pytest

from .conftest import PASSWORD, TOTP, USERNAME, Harness, file_mode, free_port
from .leak_check import find_secret_in_paths, find_secret_in_text

AUTH_FAIL_CODES = {1, 2}  # falsches Passwort/TOTP: nicht 0 und nicht 3/4/5 (siehe INTERFACE.md)


def kc_posts(h: Harness):
    return [r for r in h.world.requests_to("keycloak") if r.method == "POST"]


def assert_logged_in(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    return r


# ---------------------------------------------------------------- CLI-Grundlagen
def test_help_lists_commands(h: Harness):
    """F1: login/status/logout existieren."""
    r = h.run("--help")
    assert r.exit_code == 0, str(r)
    for cmd in ("login", "status", "logout"):
        assert cmd in r.stdout


@pytest.mark.parametrize("cmd", ["login", "status", "logout"])
def test_each_command_has_json_flag(h: Harness, cmd: str):
    """§3: `--json` für alle Befehle (als Option des Unterbefehls)."""
    r = h.run(cmd, "--help")
    assert r.exit_code == 0, str(r)
    assert "--json" in r.stdout, str(r)


# ---------------------------------------------------------------- Login-Flow (A3)
def test_login_full_keycloak_flow(h: Harness):
    """A3: openidconnect.php -> Keycloak-Formular -> TOTP -> Redirect -> Session-Cookie."""
    assert_logged_in(h)
    ilias = h.world.requests_to("ilias")
    assert any(r.path.endswith("/openidconnect.php") and "code" not in r.query for r in ilias), "Start bei openidconnect.php fehlt"
    assert any(r.path.endswith("/openidconnect.php") and "code" in r.query for r in ilias), "Redirect mit code zurück zu ILIAS nicht gefolgt"
    posts = kc_posts(h)
    assert len(posts) == 2, f"erwartet 2 POSTs an Keycloak (Passwort, TOTP), bekommen {len(posts)}"
    assert posts[0].form.get("username") == [USERNAME]
    assert posts[1].form.get("otp") == [TOTP]


def test_login_posts_form_action_and_hidden_fields(h: Harness):
    """A3: action-URL inkl. session_code/execution/tab_id und alle hidden inputs werden übernommen."""
    assert_logged_in(h)
    for p in kc_posts(h):
        for key in ("session_code", "execution", "client_id", "tab_id"):
            assert key in p.query, f"Query-Parameter {key} der Formular-action fehlt: {p.query}"
        assert "kc_acceptance_nonce" in p.form, "hidden input nicht mitgesendet"
    assert "credentialId" in kc_posts(h)[0].form, "hidden input credentialId nicht mitgesendet"


def test_user_agent_is_ilias_cli(h: Harness):
    """N2: eigener User-Agent `ilias-cli/x.y`."""
    assert_logged_in(h)
    uas = {r.headers.get("User-Agent", "") for r in h.world.requests}
    assert uas and all(ua.startswith("ilias-cli/") for ua in uas), uas


def test_login_json_output(h: Harness):
    """F1/§3: `ilias login --json` liefert JSON, ohne Cookies."""
    r = h.login("--json")
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert isinstance(data, dict)
    for sid in h.world.issued_session_ids:
        assert sid not in r.stdout and sid not in r.stderr, "Session-Cookie in Ausgabe (A4)"


def test_wrong_password(h: Harness):
    """A3: falsches Passwort wird erkannt, kein TOTP-Schritt, keine Session."""
    r = h.login(password="falsches-Passwort-123")
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    assert not any("otp" in p.form for p in kc_posts(h)), "TOTP gesendet trotz falschem Passwort"
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_wrong_totp(h: Harness):
    """A2/A3: falscher TOTP-Code wird erkannt, keine Session."""
    r = h.login(totp="000000")
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_unexpected_html_exit_5(h: Harness):
    """§3: Parser-Fehler (kein Keycloak-Formular) -> Exit 5."""
    h.world.keycloak_auth_mode = "garbage"
    r = h.login()
    assert r.exit_code == 5, str(r)


def test_network_error_exit_4(h: Harness):
    """§3: Netzwerkfehler (Server nicht erreichbar) -> Exit 4."""
    h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
    r = h.login()
    assert r.exit_code == 4, str(r)


def test_server_error_during_login_exit_4(h: Harness):
    """§3: Serverfehler (502 von Keycloak) -> Exit 4."""
    h.world.keycloak_post_mode = "error502"
    r = h.login()
    assert r.exit_code == 4, str(r)


# ---------------------------------------------------------------- status / logout (F1, A5)
def test_status_without_session_exit_2(h: Harness):
    r = h.run("status")
    assert r.exit_code == 2, str(r)


def test_status_without_session_json(h: Harness):
    r = h.run("status", "--json")
    assert r.exit_code == 2, str(r)
    if r.stdout.strip():
        r.json()  # wenn etwas auf stdout steht, muss es gültiges JSON sein


def test_status_after_login_ok(h: Harness):
    assert_logged_in(h)
    r = h.run("status")
    assert r.exit_code == 0, str(r)


def test_status_json_logged_in_without_cookies(h: Harness):
    """§3/A4: `status --json` ist reines JSON und enthält keine Cookies."""
    assert_logged_in(h)
    r = h.run("status", "--json")
    assert r.exit_code == 0, str(r)
    assert isinstance(r.json(), dict), str(r)
    for sid in h.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr


def test_status_expired_exit_3_without_relogin(h: Harness):
    """A5: abgelaufene Session (Redirect auf login.php) -> Exit 3, kein automatischer Re-Login."""
    assert_logged_in(h)
    h.world.expire_all_sessions()
    n_before = len(h.world.requests)
    r = h.run("status")
    assert r.exit_code == 3, str(r)
    after = h.world.requests[n_before:]
    assert not any(x.server == "keycloak" for x in after), "Re-Login bei Keycloak versucht (A5)"
    assert not any(x.path.endswith("/openidconnect.php") for x in after), "Re-Login über openidconnect.php versucht (A5)"


def test_status_expired_json(h: Harness):
    assert_logged_in(h)
    h.world.expire_all_sessions()
    r = h.run("status", "--json")
    assert r.exit_code == 3, str(r)
    if r.stdout.strip():
        r.json()


def test_status_server_error_exit_4(h: Harness):
    assert_logged_in(h)
    h.world.dashboard_mode = "error503"
    r = h.run("status")
    assert r.exit_code == 4, str(r)


def test_status_network_error_exit_4(h: Harness):
    assert_logged_in(h)
    h.world.stop_ilias()
    r = h.run("status")
    assert r.exit_code == 4, str(r)


def test_logout_removes_session(h: Harness):
    """F1/A4: logout löscht die Session (Keyring und Datei)."""
    assert_logged_in(h)
    r = h.run("logout", "--json")
    assert r.exit_code == 0, str(r)
    assert isinstance(r.json(), dict), str(r)
    assert h.session_artifacts() == [], f"Session-Cookie nach logout noch gespeichert: {h.session_artifacts()}"
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_logout_without_session_ok(h: Harness):
    r = h.run("logout")
    assert r.exit_code == 0, str(r)


# ---------------------------------------------------------------- Speicherung (A4, A6)
def test_session_stored_in_keyring_or_0600_file(h: Harness):
    """A4: Cookies im Keyring oder in Datei mit 0600; nie im Arbeitsverzeichnis (Repo)."""
    assert_logged_in(h)
    artifacts = h.session_artifacts()
    assert artifacts, "Session-Cookie wurde nirgends gespeichert"
    for p in artifacts:
        assert h.cwd not in p.parents, f"Session im Arbeitsverzeichnis gespeichert: {p}"
        if p == h.keyring_file:
            continue
        if os.name != "nt":
            assert file_mode(p) == 0o600, f"{p} hat Rechte {oct(file_mode(p))}, erwartet 0600"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Rechte")
def test_file_fallback_0600_without_keyring(h: Harness):
    """A4: ohne nutzbaren Keyring -> Datei mit 0600; status funktioniert damit."""
    h.keyring_mode = "none"
    assert_logged_in(h)
    artifacts = [p for p in h.session_artifacts() if p != h.keyring_file]
    assert artifacts, "Kein Datei-Fallback geschrieben"
    for p in artifacts:
        assert file_mode(p) == 0o600, f"{p} hat Rechte {oct(file_mode(p))}"
    r = h.run("status")
    assert r.exit_code == 0, str(r)


def test_only_ilias_cookies_are_stored(h: Harness):
    """A3/A4: nur das ILIAS-Session-Cookie übernehmen, keine Keycloak-SSO-Cookies (KEYCLOAK_IDENTITY)."""
    assert_logged_in(h)
    assert h.files_containing("KEYCLOAK_IDENTITY") == [], "Keycloak-Identity-Cookie gespeichert"
    assert h.files_containing("AUTH_SESSION_ID") == [], "Keycloak-Auth-Session-Cookie gespeichert"


# ---------------------------------------------------------------- Geheimnisse (A1, A2)
LEAK_SCENARIOS = ["success", "wrong_password", "wrong_totp", "garbage_html", "server_error", "network_error"]


@pytest.mark.parametrize("scenario", LEAK_SCENARIOS)
def test_password_never_in_output_or_files(h: Harness, scenario: str):
    """A1: Passwort nie in stdout/stderr (inkl. Tracebacks/Reprs), nie in gespeicherten Dateien/Keyring."""
    if scenario == "wrong_totp":
        h.login(totp="000000")
    elif scenario == "garbage_html":
        h.world.keycloak_auth_mode = "garbage"
        h.login()
    elif scenario == "server_error":
        h.world.keycloak_post_mode = "error502"
        h.login()
    elif scenario == "network_error":
        h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
        h.login()
    elif scenario == "wrong_password":
        h.login(password=PASSWORD + "-x")
    else:
        h.login()
        h.run("status")
        h.run("status", "--json")
    if scenario in ("success", "wrong_password", "wrong_totp", "server_error") and not any(
        "password" in p.form for p in kc_posts(h)
    ):
        pytest.skip("Login-Flow hat Keycloak nie erreicht, Leak-Check hier nicht aussagekräftig")
    assert not find_secret_in_text(PASSWORD, h.all_output()), "Passwort in Ausgabe!\n" + h.all_output()
    hits = find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd, h.keyring_file.parent])
    assert hits == [], f"Passwort in Dateien: {hits}"


def test_totp_code_not_stored(h: Harness):
    """A2: kein TOTP (Code oder Secret) wird gespeichert."""
    assert_logged_in(h)
    assert h.files_containing(TOTP) == [], "TOTP-Code gespeichert"
    for p in h.written_files():
        text = p.read_text("utf-8", "replace").lower()
        assert "totp_secret" not in text and "otpauth://" not in text, f"TOTP-Secret-Spuren in {p}"


def test_password_prompt_is_hidden(h: Harness):
    """A1: kein Passwort per Kommandozeilen-Flag möglich (nur verdeckter Prompt)."""
    r = h.run("login", "--help")
    assert "--password" not in r.stdout, "login bietet ein --password-Flag an"


# ---------------------------------------------------------------- Konfiguration (N6, N7)
def test_default_config_path_in_home(h: Harness):
    """N6: ~/.config/ilias-cli/config.toml wird gelesen (ohne ILIAS_CLI_CONFIG_DIR)."""
    h.use_config_dir_env = False
    (h.config_dir / "config.toml").unlink()
    h.write_config(path=h.home / ".config" / "ilias-cli" / "config.toml")
    assert_logged_in(h)
    assert h.world.requests_to("ilias"), "config.toml in ~/.config/ilias-cli wurde nicht benutzt"
    r = h.run("status")
    assert r.exit_code == 0, str(r)


def test_base_url_with_path_prefix(tmp_path):
    """N7: andere ILIAS-Instanz mit Pfad-Präfix (z. B. https://host/ilias) über base_url konfigurierbar."""
    from .fake_servers import FakeWorld

    w = FakeWorld(username=USERNAME, password=PASSWORD, totp=TOTP, ilias_prefix="/ilias").start()
    try:
        h = Harness(tmp_path, w)
        r = h.login()
        assert r.exit_code == 0, str(r)
        s = h.run("status")
        assert s.exit_code == 0, str(s)
    finally:
        w.stop()
