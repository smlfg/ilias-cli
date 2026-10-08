"""Moodle-Login: login/status/logout gegen einen lokalen Fake-Moodle (127.0.0.1).

Dekorate jeder Test die Anforderungen aus ANFORDERUNGEN.md, die er prüft.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from acceptance.leak_check import find_secret_in_paths, find_secret_in_text

from .conftest import (
    INSTANCE,
    PASSWORD,
    USERNAME,
    Harness,
    RunResult,
    file_mode,
    free_port,
)

AUTH_FAIL_CODES = {1, 2}  # INTERFACE.md §3: falsches Passwort ist ein Auth-Fehler


def assert_json_ok(result: RunResult, command: str) -> dict:
    data = result.json()
    assert isinstance(data, dict), str(result)
    assert data["ok"] is True, str(result)
    assert data["command"] == command, str(result)
    assert data["instance"] == INSTANCE, str(result)
    assert data["lms"] == "moodle", str(result)
    # N5: ISO 8601 mit Zeitzone
    stamp = datetime.fromisoformat(data["timestamp"])
    assert stamp.tzinfo is not None, str(result)
    assert str(stamp.utcoffset()) in {"2:00:00", "1:00:00"}, str(result)
    return data


def assert_json_error(result: RunResult, command: str, exit_code: int, code: str | None = None) -> dict:
    data = result.json()
    assert data["ok"] is False, str(result)
    assert data["command"] == command, str(result)
    assert data["exit_code"] == exit_code == result.exit_code, str(result)
    assert data["error"]["code"] == (code or data["error"]["code"]), str(result)
    assert data["error"]["message"], str(result)
    return data


def assert_logged_in(h: Harness) -> RunResult:
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    return result


# ------------------------------------------------------------------ Kommandos
def test_help_lists_commands(h: Harness):
    """F1: login/status/logout existieren; `ilias --help` funktioniert."""
    result = h.run("--help")
    assert result.exit_code == 0, str(result)
    for command in ("login", "status", "logout"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["login", "status", "logout"])
def test_each_command_has_json_and_instance_flag(h: Harness, command: str):
    """INTERFACE.md §2/§4: `--json` ist Option des Unterbefehls, `--instance` wählt die Instanz."""
    result = h.run(command, "--help")
    assert result.exit_code == 0, str(result)
    assert "--json" in result.stdout, str(result)
    assert "--instance" in result.stdout, str(result)


def test_login_help_has_no_password_flag(h: Harness):
    """A1: es gibt kein `--password`-Flag."""
    result = h.run("login", "--help")
    assert result.exit_code == 0, str(result)
    assert "--password" not in result.stdout


# ------------------------------------------------------------------ Login
def test_login_success(h: Harness):
    """F1: Erfolgreicher Login, Session gespeichert, Name/Plattform gemeldet."""
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert "hs.mannheim.student" in result.stdout
    assert "Erika Musterfrau" in result.stdout
    assert "Lernplattform TH-MA" in result.stdout


def test_login_uses_moodle_mobile_webservice(h: Harness):
    """real-fixtures/NOTES.md: token.php mit service=moodle_mobile_app, dann REST-Verifikation."""
    assert_logged_in(h)
    token_request = h.world.last_token_php()
    assert token_request is not None, "kein POST an /login/token.php"
    assert token_request.method == "POST"
    assert token_request.form_value("username") == USERNAME
    assert token_request.form_value("password") == PASSWORD
    assert token_request.form_value("service") == "moodle_mobile_app"

    rest_request = h.world.last_rest()
    assert rest_request is not None, "core_webservice_get_site_info wurde nicht aufgerufen"
    assert rest_request.form_value("wsfunction") == "core_webservice_get_site_info"
    assert rest_request.form_value("moodlewsrestformat") == "json"
    assert (rest_request.form_value("wstoken") or "").startswith("tok-")
    # Verifikation passiert VOR dem Speichern: erst Site-Info, dann gilt der Login als erfolgreich
    assert len(h.world.requests_to("/login/token.php")) == 1
    assert len(h.world.requests_to("/webservice/rest/server.php")) >= 1


def test_user_agent_is_ilias_cli(h: Harness):
    """N2: eigener User-Agent `ilias-cli/<version>`."""
    assert_logged_in(h)
    agents = {r.headers.get("User-Agent", "") for r in h.world.requests}
    assert agents and all(a.startswith("ilias-cli/") for a in agents), agents


def test_base_url_from_config_is_used(h: Harness):
    """N7: das eingebaute Profil wird nur durch config.toml überschrieben (Base-URL des Fake-Servers)."""
    result = h.login("--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    assert result.json()["base_url"] == h.world.base_url


def test_default_instance_from_config(h: Harness):
    """INTERFACE.md §4: `instance = "hs-mannheim"` in config.toml genügt, `--instance` ist optional."""
    result = h.login()
    assert result.exit_code == 0, str(result)
    assert h.world.last_token_php() is not None


def test_login_json_shape(h: Harness):
    """§3/§2: genau ein JSON-Objekt auf stdout, ohne Token."""
    result = h.login("--instance", INSTANCE, "--json")
    data = assert_json_ok(result, "login")
    assert result.stdout.strip().startswith("{"), "stdout muss mit dem JSON-Objekt beginnen"
    assert set(data) == {
        "ok",
        "command",
        "instance",
        "lms",
        "base_url",
        "username",
        "fullname",
        "sitename",
        "userid",
        "verified",
        "token_stored",
        "timestamp",
    }, sorted(data)
    assert data["base_url"] == h.world.base_url
    assert data["username"] == USERNAME
    assert data["fullname"] == "Erika Musterfrau"
    assert data["sitename"] == "Lernplattform TH-MA"
    assert data["userid"] == 4711
    assert data["verified"] is True and data["token_stored"] is True


# ------------------------------------------------------------------ Fehler beim Login
def test_wrong_password(h: Harness):
    """A1/§3: falsches Passwort -> Auth-Fehler mit klarer Meldung, keine Session."""
    result = h.login("--instance", INSTANCE, password="falsches-Passwort-123")
    assert result.exit_code in AUTH_FAIL_CODES, str(result)
    assert "invalidlogin" in (result.stdout + result.stderr) or "abgelehnt" in (result.stdout + result.stderr)
    assert not h.session_artifacts(), "Session trotz falschem Passwort gespeichert"
    status = h.status("--instance", INSTANCE)
    assert status.exit_code == 2, str(status)


def test_wrong_password_json(h: Harness):
    result = h.login("--instance", INSTANCE, "--json", password="falsches-Passwort-123")
    assert result.exit_code in AUTH_FAIL_CODES, str(result)
    data = assert_json_error(result, "login", result.exit_code, "auth_failed")
    assert "invalidlogin" in data["error"]["message"]


def test_server_error_5xx_exit_4(h: Harness):
    """§3: HTTP 5xx -> Exit 4 (Netzwerk/Server)."""
    h.world.token_mode = "server_error"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 4, str(result)
    assert not h.session_artifacts()


def test_server_error_during_verification_exit_4(h: Harness):
    """§3: auch die Verifikation kann 5xx liefern -> Exit 4, und nichts wird gespeichert."""
    h.world.rest_mode = "server_error"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 4, str(result)
    assert not h.session_artifacts(), "Token gespeichert, obwohl die Verifikation fehlschlug"
    assert h.status("--instance", INSTANCE).exit_code == 2


def test_network_error_exit_4(h: Harness):
    """§3: Server nicht erreichbar -> Exit 4."""
    h.world.stop()
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_unexpected_html_exit_5(h: Harness):
    """§3: HTML statt JSON -> Exit 5 (Parser-Fehler)."""
    h.world.token_mode = "html"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 5, str(result)
    assert not h.session_artifacts()


def test_unexpected_html_during_verification_exit_5(h: Harness):
    """Token wird erst nach erfolgreicher Verifikation gespeichert."""
    h.world.rest_mode = "html"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 5, str(result)
    assert not h.session_artifacts()


def test_invalid_token_during_verification_exit_3(h: Harness):
    """Moodle lehnt den frisch ausgestellten Token ab -> Exit 3, nichts gespeichert."""
    h.world.rest_mode = "invalid_token"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 3, str(result)
    assert not h.session_artifacts()


def test_token_response_without_token_exit_5(h: Harness):
    """Parser-Fehler: Antwort ohne Token-Feld."""
    h.world.token_mode = "empty"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 5, str(result)


# ------------------------------------------------------------------ Status
def test_status_after_login(h: Harness):
    """F1: gültige Session -> Exit 0."""
    assert_logged_in(h)
    result = h.status("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert USERNAME in result.stdout


def test_status_json_shape(h: Harness):
    assert_logged_in(h)
    result = h.status("--instance", INSTANCE, "--json")
    data = assert_json_ok(result, "status")
    assert set(data) == {
        "ok",
        "command",
        "instance",
        "lms",
        "base_url",
        "username",
        "fullname",
        "sitename",
        "userid",
        "logged_in",
        "timestamp",
    }, sorted(data)
    assert data["logged_in"] is True
    assert data["username"] == USERNAME


def test_status_without_token_exit_2(h: Harness):
    """§3: keine gespeicherte Session -> Exit 2."""
    result = h.status("--instance", INSTANCE)
    assert result.exit_code == 2, str(result)


def test_status_without_token_json(h: Harness):
    result = h.status("--instance", INSTANCE, "--json")
    assert_json_error(result, "status", 2, "not_logged_in")


def test_status_with_invalid_token_exit_3(h: Harness):
    """A5: Token vom Server nicht mehr akzeptiert (invalidtoken) -> Exit 3, kein Re-Login."""
    assert_logged_in(h)
    h.world.expire_tokens()
    requests_before = len(h.world.requests)
    result = h.status("--instance", INSTANCE)
    assert result.exit_code == 3, str(result)
    # A5: kein automatischer Re-Login (kein weiterer POST auf token.php)
    assert len(h.world.requests_to("/login/token.php")) == 1, "Re-Login trotz abgelaufener Session"
    rest_calls = h.world.requests[requests_before:]
    assert all(r.path != "/login/token.php" for r in rest_calls)
    # Der unbrauchbare Token wird lokal entfernt
    assert h.status("--instance", INSTANCE).exit_code == 2


def test_status_invalid_token_json(h: Harness):
    assert_logged_in(h)
    h.world.expire_tokens()
    result = h.status("--instance", INSTANCE, "--json")
    assert_json_error(result, "status", 3, "session_expired")


def test_status_network_error_exit_4(h: Harness):
    """§3: Server nicht erreichbar -> Exit 4."""
    assert_logged_in(h)
    h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
    result = h.status("--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_status_server_error_exit_4(h: Harness):
    assert_logged_in(h)
    h.world.rest_mode = "server_error"
    assert h.status("--instance", INSTANCE).exit_code == 4


# ------------------------------------------------------------------ Logout
def test_logout_removes_token(h: Harness):
    """F1/A4: logout löscht den Token aus Keyring und Datei."""
    assert_logged_in(h)
    assert h.session_artifacts(), "Token wurde nirgends gespeichert"
    result = h.logout("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert h.session_artifacts() == [], f"Token nach logout noch gespeichert: {h.session_artifacts()}"
    assert h.keyring_entries() == {}, f"Keyring nach logout nicht leer: {h.keyring_entries()}"
    assert h.status("--instance", INSTANCE).exit_code == 2


def test_logout_json_shape(h: Harness):
    assert_logged_in(h)
    result = h.logout("--instance", INSTANCE, "--json")
    data = assert_json_ok(result, "logout")
    assert set(data) == {"ok", "command", "instance", "lms", "token_removed", "timestamp"}, sorted(data)
    assert data["token_removed"] is True


def test_logout_without_session_ok(h: Harness):
    """§2: logout ist auch ohne Session erfolgreich (Exit 0)."""
    result = h.logout("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    again = h.logout("--instance", INSTANCE, "--json")
    assert again.exit_code == 0, str(again)
    assert assert_json_ok(again, "logout")["token_removed"] is False


# ------------------------------------------------------------------ Speicherung (A4)
def test_token_in_keyring(h: Harness):
    """A4: Token im Schlüsselbund, nicht als Datei."""
    assert_logged_in(h)
    entries = h.keyring_entries()
    assert len(entries) == 1, entries
    stored = next(iter(entries.values()))
    assert stored.startswith("tok-")
    assert not h.token_file.exists(), "Token zusätzlich als Datei abgelegt"


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte")
def test_file_fallback_0600_without_keyring(h: Harness):
    """A4: ohne nutzbaren Keyring eine Datei mit 0600, angelegt von Anfang an."""
    h.keyring_mode = "none"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert h.token_file.exists(), "kein Datei-Fallback geschrieben"
    assert file_mode(h.token_file) == 0o600, oct(file_mode(h.token_file))
    assert file_mode(h.token_file.parent) == 0o700, oct(file_mode(h.token_file.parent))
    # und damit funktioniert der Status
    assert h.status("--instance", INSTANCE).exit_code == 0
    # logout löscht auch die Datei
    assert h.logout("--instance", INSTANCE).exit_code == 0
    assert not h.token_file.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte")
def test_token_file_never_widened(h: Harness):
    """A1/A4: keine Restdatei mit zu weiten Rechten im Session-Ordner."""
    h.keyring_mode = "none"
    assert_logged_in(h)
    assert_logged_in(h)
    for path in (h.config_dir / "sessions").iterdir():
        assert file_mode(path) == 0o600, f"{path} hat Rechte {oct(file_mode(path))}"


def test_session_never_written_into_workdir(h: Harness):
    """A4/INTERFACE.md §4: nichts wird ins Arbeitsverzeichnis geschrieben."""
    assert_logged_in(h)
    assert list(h.cwd.iterdir()) == [], f"Dateien im Arbeitsverzeichnis: {list(h.cwd.iterdir())}"


# ------------------------------------------------------------------ Geheimnisse (A1, A4)
def test_password_never_in_output_or_files(h: Harness):
    """A1: Passwort nie in stdout/stderr (auch nicht im Traceback) und nie in Dateien."""
    assert_logged_in(h)
    h.status("--instance", INSTANCE)
    h.status("--instance", INSTANCE, "--json")
    assert not find_secret_in_text(PASSWORD, h.all_output()), "Passwort in der Ausgabe!"
    hits = find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd, h.keyring_file.parent])
    assert hits == [], f"Passwort in Dateien: {hits}"


def test_password_not_stored_on_failure(h: Harness):
    """A1: auch bei Fehlern (401, 5xx, HTML) wird das Passwort nirgends abgelegt."""
    for mode, expect in (("access_denied", 1), ("server_error", 4), ("html", 5)):
        h.keyring_mode = "none"  # Datei-Fallback: dann wäre ein Leak überhaupt sichtbar
        h.world.token_mode = mode
        result = h.login("--instance", INSTANCE)
        assert result.exit_code == expect, f"{mode}: {result}"
        hits = find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd, h.keyring_file.parent])
        assert hits == [], f"Passwort in Dateien ({mode}): {hits}"
        assert not find_secret_in_text(PASSWORD, h.all_output()), f"Passwort in Ausgabe ({mode})"
        h.world.token_mode = "normal"


def test_token_never_printed(h: Harness):
    """A4: der Token erscheint in keiner Ausgabe."""
    assert_logged_in(h)
    tokens = list(h.world.tokens)
    assert tokens
    for command in (h.status("--instance", INSTANCE), h.status("--instance", INSTANCE, "--json")):
        assert command.exit_code == 0, str(command)
        for token in tokens:
            assert token not in command.stdout + command.stderr, "Token in der Ausgabe"
    # ... und steht nur im Keyring bzw. in der 0600-Datei
    assert sorted(h.files_containing(tokens[0])) == h.session_artifacts()
    assert set(h.session_artifacts()) <= {h.keyring_file, h.token_file}


def test_stored_session_only_contains_token(h: Harness):
    """A4: gespeichert wird nur der Token, kein Passwort, kein TOTP."""
    assert_logged_in(h)
    entries = h.keyring_entries()
    values = list(entries.values())
    assert values == [v for v in values if v.startswith("tok-")]
    assert len(values) == 1


def test_server_error_text_cannot_leak_password(h: Harness):
    """A1: spiegelt der Server das Passwort in einer Fehlermeldung, wird es entfernt."""
    h.world.token_mode = "echo_password"
    result = h.login("--instance", INSTANCE)
    assert result.exit_code in AUTH_FAIL_CODES, str(result)
    assert "***" in result.stderr, "Passwort wurde nicht geschwärzt"
    assert not find_secret_in_text(PASSWORD, h.all_output()), h.all_output()


def test_server_error_text_cannot_leak_token(h: Harness):
    """A4: spiegelt der Server den Token in einer Fehlermeldung, wird er entfernt."""
    assert_logged_in(h)
    token = next(iter(h.world.tokens))
    h.world.rest_mode = "echo_token"
    result = h.status("--instance", INSTANCE)
    assert result.exit_code == 3, str(result)
    assert token not in result.stdout + result.stderr, "Token in der Ausgabe"
    assert "***" in result.stderr
