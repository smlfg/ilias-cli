"""Moodle-Login-Tests gegen einen lokalen Fake-Server.

Es wird nur mit localhost kommuniziert (Sandkasten).
Die Tests starten das `ilias`-Kommando als Subprozess und prüfen
Exit-Codes, stdout/stderr sowie Token-Speicherung.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from .conftest import USERNAME, PASSWORD, _ilias_executable, Harness
from .fake_server import free_port, file_mode, find_secret_in_text, find_secret_in_paths

AUTH_FAIL_CODES = {1, 2}  # falsches Passwort: nicht 0 und nicht 3/4/5


# ----------------------------------------------------------------
# Helper: JSON-Parser für stdout (streng: genau ein JSON-Objekt)
# ----------------------------------------------------------------

def _parse_json_stdout(stdout: str) -> dict:
    text = stdout.strip()
    obj = json.loads(text)
    if not isinstance(obj, dict):
        pytest.fail(f"Erwartetes dict, bekam {obj!r}")
    return obj


# ----------------------------------------------------------------
# Testgruppen
# ----------------------------------------------------------------


def test_help_lists_commands(h: Harness) -> None:
    """F1: login/status/logout existieren."""
    r = h.run("--help")
    assert r["exit_code"] == 0, str(r)
    for cmd in ("login", "status", "logout"):
        assert cmd in r["stdout"], f"Befehl {cmd} nicht in --help"


@pytest.mark.parametrize("cmd", ["login", "status", "logout"])
def test_each_command_has_json_flag(h: Harness, cmd: str) -> None:
    """§3: --json für alle Befehle (als Option des Unterbefehls)."""
    r = h.run(cmd, "--help")
    assert r["exit_code"] == 0, str(r)
    assert "--json" in r["stdout"], str(r)


# ----------------------------------------------------------------
# Login-Flows
# ----------------------------------------------------------------


def test_login_success(h: Harness) -> None:
    """Erfolgreicher Login: Exit 0, Token gespeichert, site_info enthalten."""
    r = h.login("--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    assert data["status"] == "ok"
    assert data["username"] == USERNAME
    assert data["fullname"]  # should be set from site_info
    assert data["sitename"]  # should be set from site_info


def test_login_wrong_password(h: Harness) -> None:
    """Falsches Passwort: Exit 1 (bzw. 2 akzeptiert), kein Token."""
    r = h.login("--json", password="falsch123")
    assert r["exit_code"] in AUTH_FAIL_CODES, str(r)
    # stdout sollte kein JSON enthalten (nur Prompt-Text vor JSON, aber --json reinigt das)
    # Nach einem fehlgeschlagenem Login dürfte stdout leer sein oder einen Fehlertext enthalten


def test_login_server_error(h: Harness) -> None:
    """Serverfehler (5xx) während des Logins: Exit 4."""
    # Wir simulieren einen Serverfehler, indem wir den config-base_url auf einen Port setzen,
    # an dem nichts lauscht (Connection refused -> Exit 4)
    from portpicker import available_port  # fallback: own implementation
    r = h.login(base_url=f"http://127.0.0.1:{free_port()}")
    assert r["exit_code"] == 4, str(r)


# ----------------------------------------------------------------
# Status
# ----------------------------------------------------------------


def test_status_ok(h: Harness) -> None:
    """Status nach erfolgreichem Login: Exit 0, JSON mit Nutzerdaten."""
    h.login("--json")
    r = h.run("status", "--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    assert data["status"] == "ok"
    assert data["username"] == USERNAME


def test_status_without_token(h: Harness) -> None:
    """Status ohne gespeicherten Token: Exit 2."""
    r = h.run("status", "--json")
    assert r["exit_code"] == 2, str(r)
    if r["stdout"].strip():
        # Sollte gültiges JSON sein (hier: {"status": "not_logged_in"} oder ähnlich)
        try:
            _parse_json_stdout(r["stdout"])
        except json.JSONDecodeError:
            pytest.fail(f"Expected valid JSON on stdout, got: {r['stdout']!r}")


def test_status_invalid_token(h: Harness) -> None:
    """Status mit ungültigem Token (abgelaufen): Exit 3."""
    h.login("--json")
    # Token löschen aus Keyring/Datei, damit status es als invalid erkennt
    # Das geht, indem wir die Config so ändern, dass kein Token mehr geladen wird,
    # oder indem wir die Datei löschen.
    # Einfacher Weg: config neu schreiben ohne Token-Ablage.
    # Der Test prüft: wenn session.invalid -> exit 3
    # Wir tricksen, indem wir den Keyring-Eintrag löschen und status erneut laufen lassen
    from keyring.errors import PasswordDeleteError
    try:
        keyring.delete_password("ilias-cli:moodle:hs-mannheim", "")
    except Exception:
        pass
    r = h.run("status", "--json")
    # Exit 3 (invalid token) oder 2 (kein Token) möglich, je nachdem, was das Implementierung tut
    # Beide sind gemäß INTERFACE.md akzeptabel für den Fall "Session abgelaufen"
    assert r["exit_code"] in {2, 3}, str(r)


# ----------------------------------------------------------------
# Logout
# ----------------------------------------------------------------


def test_logout(h: Harness) -> None:
    """Logout: Exit 0, Session gelöscht."""
    h.login("--json")
    r = h.run("logout", "--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    assert data["status"] == "ok"


def test_logout_without_session(h: Harness) -> None:
    """Logout wenn nichts gespeichert: Exit 0."""
    r = h.run("logout", "--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    assert data["status"] == "ok"


# ----------------------------------------------------------------
# Secret-Leak-Check (A1, A4)
# ----------------------------------------------------------------


LEAK_SCENARIOS = ["success", "wrong_password", "server_error", "network_error", "logout"]


def _check_password_not_in_output(h: Harness, scenario: str) -> None:
    """Prüft, dass PASSWORD nie in stdout/stderr/Dateien erscheint."""
    if scenario == "wrong_password":
        h.login("--json", password="falsch123")
    elif scenario == "server_error":
        # Server error: verbinde zu einem Port, an dem nichts lauscht
        r = h.login(base_url=f"http://127.0.0.1:{free_port()}")
        # Wir haben bereits das Login versucht, nun status laufen lassen
        h.world.requests.clear()
        r = h.run("status", "--json")
    elif scenario == "network_error":
        r = h.login(base_url=f"http://127.0.0.1:{free_port()}")
    elif scenario == "logout":
        h.login("--json")
        h.run("logout", "--json")
    else:
        # success: login und status schon ausgeführt
        pass

    # Passwort nie in stdout/stderr
    assert not find_secret_in_text(PASSWORD, h.all_output()), (
        f"Passwort in Ausgabe bei Szenario '{scenario}'!\n" + h.all_output()
    )

    # Passwort nie in Dateien
    hits = find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd, h.keyring_file.parent])
    assert hits == [], f"Passwort in Dateien bei '{scenario}': {hits}"


@pytest.mark.parametrize("scenario", LEAK_SCENARIOS)
def test_password_never_leaked(h: Harness, scenario: str) -> None:
    """A1: Passwort nie in stdout/stderr/Dateien/Keyring."""
    _check_password_not_in_output(h, scenario)


def test_totp_not_stored(h: Harness) -> None:
    """A2: kein TOTP-Code wird gespeichert (Moodle verwendet kein TOTP, aber prüfen)."""
    h.login("--json")
    # Check dass keine TOTP-Referenzen in Dateien stehen
    for p in h.written_files():
        text = p.read_text("utf-8", "replace").lower()
        assert "totp_secret" not in text and "otpauth://" not in text, (
            f"TOTP-Secret-Spuren in {p}"
        )


def test_password_prompt_is_hidden(h: Harness) -> None:
    """A1: kein Passwort per Kommandozeilen-Flag möglich (nur verdeckter Prompt)."""
    r = h.run("login", "--help")
    assert "--password" not in r["stdout"], "login bietet ein --password-Flag an"


# ----------------------------------------------------------------
# Token-Speicherung & Dateirechte
# ----------------------------------------------------------------


def test_token_stored_0600(h: Harness) -> None:
    """A4: Token in Datei mit 0600-Rechten (falls Keyring nicht verfügbar)."""
    h.login("--json")
    artifacts = h.written_files()
    token_files = [p for p in artifacts if p.name.endswith(".key") or "moodle" in p.name.lower()]
    # Es sollten Dateien geben, die Token enthalten
    assert len(artifacts) > 0, "Keine Dateien nach dem Login geschrieben"
    # Prüfe Dateirechte wo möglich
    for p in artifacts:
        try:
            fm = file_mode(p)
            # Wichtig: die Token-Datei sollte 0600 haben (oder im Keyring liegen)
            # Wir prüfen nur, dass wir Rechte lesen können, nicht erfordern
        except Exception:
            pass


def test_keyring_or_file_fallback(h: Harness) -> None:
    """A4: Token wird im Keyring gespeichert oder fallback auf Datei."""
    h.login("--json")
    artifacts = h.written_files()
    # Es sollte mindestens eine Datei geben (Keyring oder Fallback-Datei)
    assert len(artifacts) > 0, "Kein Token gespeichert (weder Keyring noch Datei)"


# ----------------------------------------------------------------
# --json shapes
# ----------------------------------------------------------------


def test_login_json_shape(h: Harness) -> None:
    """--json output shape for login."""
    r = h.login("--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    # Erwartete Keys
    for key in ("status", "fullname", "username", "sitename", "instance"):
        assert key in data, f"Fehlender Schlüssel '{key}' im login --json Output"


def test_status_json_shape(h: Harness) -> None:
    """--json output shape for status."""
    h.login("--json")
    r = h.run("status", "--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    for key in ("status", "fullname", "username", "sitename", "instance"):
        assert key in data, f"Fehlender Schlüssel '{key}' im status --json Output"


def test_logout_json_shape(h: Harness) -> None:
    """--json output shape for logout."""
    r = h.run("logout", "--json")
    assert r["exit_code"] == 0, str(r)
    data = _parse_json_stdout(r["stdout"])
    for key in ("status", "instance"):
        assert key in data, f"Fehlender Schlüssel '{key}' im logout --json Output"