"""Moodle Backend Tests: login, status, logout, JSON, Security."""

from __future__ import annotations

import os
import sys

import pytest

from tests.acceptance.leak_check import find_secret_in_paths, find_secret_in_text
from tests.moodle.conftest import MoodleHarness, PASSWORD, USERNAME, free_port

AUTH_FAIL_CODES = {1, 2}


def test_help_lists_commands(m: MoodleHarness):
    r = m.run("--help")
    assert r.exit_code == 0, str(r)
    for cmd in ("login", "status", "logout", "config-show"):
        assert cmd in r.stdout


def test_each_command_has_json_flag(m: MoodleHarness):
    for cmd in ("login", "status", "logout", "config-show"):
        r = m.run(cmd, "--help")
        assert r.exit_code == 0, str(r)
        assert "--json" in r.stdout, str(r)


# ---------------------------------------------------------------- Login
def test_login_success(m: MoodleHarness):
    r = m.login()
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert data["success"] is True
    assert data["instance"] == "test-moodle"
    assert data["lms"] == "moodle"
    assert data["username"] == USERNAME
    assert data["fullname"] == "Test User"
    assert data["sitename"] == "Lernplattform TH-MA"
    assert "token" not in data  # Token nie in JSON


def test_login_success_json_shape(m: MoodleHarness):
    r = m.login("--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert isinstance(data, dict)
    assert data["success"] is True
    assert data["exit_code"] == 0


def test_login_wrong_password(m: MoodleHarness):
    r = m.login(password="falsches-passwort")
    assert r.exit_code in AUTH_FAIL_CODES, str(r)
    data = r.json(strict=False)
    assert data["success"] is False
    assert data["errorcode"] == "invalidlogin" or "invalid" in (data.get("error") or "").lower()

    # Status prüft Exit 2
    s = m.status()
    assert s.exit_code == 2, str(s)


def test_login_unexpected_html_exit_5(m: MoodleHarness):
    m.world.token_mode = "garbage"
    r = m.login()
    assert r.exit_code == 5, str(r)


def test_login_server_error_exit_4(m: MoodleHarness):
    m.world.token_mode = "error500"
    r = m.login()
    assert r.exit_code == 4, str(r)


def test_login_network_error_exit_4(m: MoodleHarness):
    m.write_config(base_url=f"http://127.0.0.1:{free_port()}")
    r = m.login()
    assert r.exit_code == 4, str(r)


# ---------------------------------------------------------------- Status
def test_status_without_token_exit_2(m: MoodleHarness):
    r = m.status()
    assert r.exit_code == 2, str(r)


def test_status_without_token_json(m: MoodleHarness):
    r = m.status("--json")
    assert r.exit_code == 2, str(r)
    if r.stdout.strip():
        data = r.json()
        assert data["success"] is False
        assert data["logged_in"] is False


def test_status_after_login_ok(m: MoodleHarness):
    m.login()
    r = m.status()
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert data["success"] is True
    assert data["logged_in"] is True
    assert data["token_valid"] is True
    assert data["username"] == USERNAME


def test_status_json_logged_in_without_token(m: MoodleHarness):
    m.login()
    r = m.status("--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert isinstance(data, dict)
    for token in m.world.issued_tokens:
        assert token not in r.stdout + r.stderr


def test_status_expired_token_exit_3(m: MoodleHarness):
    m.login()
    m.world.expire_all_tokens()
    r = m.status()
    assert r.exit_code == 3, str(r)
    data = r.json()
    assert data["success"] is False
    assert data["errorcode"] == "invalidtoken"


def test_status_expired_token_json(m: MoodleHarness):
    m.login()
    m.world.expire_all_tokens()
    r = m.status("--json")
    assert r.exit_code == 3, str(r)
    if r.stdout.strip():
        data = r.json()
        assert data["token_valid"] is False


def test_status_server_error_exit_4(m: MoodleHarness):
    m.login()
    m.world.siteinfo_mode = "error503"
    r = m.status()
    assert r.exit_code == 4, str(r)


def test_status_network_error_exit_4(m: MoodleHarness):
    m.login()
    m.world.stop()
    r = m.status()
    assert r.exit_code == 4, str(r)


def test_status_unexpected_html_exit_5(m: MoodleHarness):
    m.login()
    m.world.siteinfo_mode = "garbage"
    r = m.status()
    assert r.exit_code == 5, str(r)


# ---------------------------------------------------------------- Logout
def test_logout_removes_token(m: MoodleHarness):
    m.login()
    assert m.token_artifacts(), "Token vor logout nicht gespeichert"
    r = m.logout("--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert data["success"] is True
    assert data["had_session"] is True
    assert m.token_artifacts() == [], f"Token nach logout noch vorhanden: {m.token_artifacts()}"
    s = m.status()
    assert s.exit_code == 2, str(s)


def test_logout_without_token_ok(m: MoodleHarness):
    r = m.logout()
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert data["success"] is True
    assert data["had_session"] is False


# ---------------------------------------------------------------- Speicherung (Security)
def test_token_stored_in_keyring_or_0600_file(m: MoodleHarness):
    m.login()
    artifacts = m.token_artifacts()
    assert artifacts, "Token wurde nirgends gespeichert"
    for p in artifacts:
        assert m.cwd not in p.parents, f"Token im Arbeitsverzeichnis: {p}"
        if p == m.keyring_file:
            continue
        if os.name != "nt":
            assert file_mode(p) == 0o600, f"{p} hat Rechte {oct(file_mode(p))}, erwartet 0600"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Rechte")
def test_file_fallback_0600_without_keyring(m: MoodleHarness):
    m.keyring_mode = "none"
    m.login()
    artifacts = [p for p in m.token_artifacts() if p != m.keyring_file]
    assert artifacts, "Kein Datei-Fallback geschrieben"
    for p in artifacts:
        assert file_mode(p) == 0o600, f"{p} hat Rechte {oct(file_mode(p))}"
    r = m.status()
    assert r.exit_code == 0, str(r)


# ---------------------------------------------------------------- Geheimnisse (Security)
LEAK_SCENARIOS = ["success", "wrong_password", "garbage_html", "server_error", "network_error"]


@pytest.mark.parametrize("scenario", LEAK_SCENARIOS)
def test_password_never_in_output_or_files(m: MoodleHarness, scenario: str):
    if scenario == "garbage_html":
        m.world.token_mode = "garbage"
        m.login()
    elif scenario == "server_error":
        m.world.token_mode = "error500"
        m.login()
    elif scenario == "network_error":
        m.write_config(base_url=f"http://127.0.0.1:{free_port()}")
        m.login()
    elif scenario == "wrong_password":
        m.login(password=PASSWORD + "-x")
    else:
        m.login()
        m.status()
        m.status("--json")

    if scenario in ("success", "wrong_password", "server_error"):
        token_posts = [r for r in m.world.requests if r.path == "/login/token.php" and r.method == "POST"]
        if not any("password" in r.form for r in token_posts):
            pytest.skip("Login-Flow hat Token-Endpunkt nie erreicht")

    assert not find_secret_in_text(PASSWORD, m.all_output()), f"Passwort in Ausgabe!\n{m.all_output()}"
    hits = find_secret_in_paths(PASSWORD, [m.home, m.config_dir, m.cwd, m.keyring_file.parent])
    assert hits == [], f"Passwort in Dateien: {hits}"


def test_token_never_in_output(m: MoodleHarness):
    m.login()
    m.status()
    m.status("--json")
    m.logout()
    for token in m.world.issued_tokens:
        assert token not in m.all_output(), f"Token in Ausgabe: {token[:20]}..."


# ---------------------------------------------------------------- Config / Instance
def test_instance_selection_via_flag(m: MoodleHarness):
    m.write_config(instance_name="custom-instance", base_url=m.world.base_url)
    r = m.run("login", "--instance", "custom-instance", input=f"{USERNAME}\n{PASSWORD}\n")
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert data["instance"] == "custom-instance"


def test_base_url_override(m: MoodleHarness):
    m.write_config(base_url=m.world.base_url, instance_name="override-test")
    r = m.run("login", "--instance", "override-test", "--base-url", m.world.base_url, input=f"{USERNAME}\n{PASSWORD}\n")
    assert r.exit_code == 0, str(r)


def test_config_show_json(m: MoodleHarness):
    r = m.run("config-show", "--instance", "test-moodle", "--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert data["lms"] == "moodle"
    assert data["base_url"] == m.world.base_url


# ---------------------------------------------------------------- User-Agent
def test_user_agent_is_ilias_cli(m: MoodleHarness):
    m.login()
    uas = {r.headers.get("User-Agent", "") for r in m.world.requests}
    assert uas and all(ua.startswith("ilias-cli/") for ua in uas), uas


# ---------------------------------------------------------------- hs-mannheim Built-in Profile
def test_builtin_hs_mannheim_profile(m: MoodleHarness):
    # Test dass das built-in Profil hs-mannheim existiert (ohne config.toml)
    m.use_config_dir_env = False
    # Config dir entfernen
    import shutil
    shutil.rmtree(m.config_dir, ignore_errors=True)
    m.home.mkdir(exist_ok=True)
    (m.home / ".config" / "ilias-cli").mkdir(parents=True, exist_ok=True)

    # Login mit --instance hs-mannheim (built-in) und --base-url auf Fake-Server
    r = m.run("login", "--instance", "hs-mannheim", "--base-url", m.world.base_url, input=f"{USERNAME}\n{PASSWORD}\n")
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert data["instance"] == "hs-mannheim"
    assert data["lms"] == "moodle"