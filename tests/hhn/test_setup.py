"""`ilias setup`: geführte Erst-Einrichtung für alle Instanzen (Spec §3).

Getestet wird der nicht-interaktive Pfad (kein TTY, Eingaben über stdin) gegen die
Fake-Server, plus Abbruch (EOF, SIGINT), Fehlversuche und Instanz-Liste/Filter. Die
interaktive Autovervollständigung selbst ist UI und wird über `--list --filter` (gleiche
Kernfunktion) geprüft. Nur synthetische Zugangsdaten.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time

import pytest
from acceptance.conftest import ilias_executable
from acceptance.leak_check import find_secret_in_paths, find_secret_in_text

from .conftest import PASSWORD, TOTP, USERNAME, HhnHarness

HHN = ("--instance", "hhn")


def assert_nothing_stored(h: HhnHarness) -> None:
    assert h.session_artifacts() == [], f"Session trotz Abbruch/Fehler gespeichert: {h.session_artifacts()}"
    s = h.run("status", *HHN)
    assert s.exit_code == 2, str(s)


def assert_no_secret_leak(h: HhnHarness) -> None:
    for secret in (PASSWORD, TOTP):
        assert not find_secret_in_text(secret, h.all_output()), f"{secret!r} in Ausgabe"
        assert not find_secret_in_paths(secret, [h.home, h.config_dir, h.cwd, h.keyring_file.parent]), f"{secret!r} in Datei"


def config_text(h: HhnHarness) -> str:
    p = h.config_dir / "config.toml"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------------------------------------------------------------- Oberfläche
def test_setup_help_no_secret_flags(hh: HhnHarness):
    """§3.1/A1: `setup` existiert; es gibt KEIN Flag für Passwort oder TOTP."""
    r = hh.run("setup", "--help")
    assert r.exit_code == 0, str(r)
    for opt in ("--instance", "--username", "--json"):
        assert opt in r.stdout, opt
    for forbidden in ("--password", "--totp", "--otp", "--code", "--secret"):
        assert forbidden not in r.stdout, forbidden


def test_setup_list_instances_json(hh: HhnHarness):
    """§3.2: `setup --list --json` zeigt alle eingebauten Instanzen und ob sie 2FA brauchen."""
    r = hh.run("setup", "--list", "--json")
    assert r.exit_code == 0, str(r)
    data = json.loads(r.stdout)
    inst = {i["key"]: i for i in data["instances"]}
    assert {"hhn", "uni-mannheim", "hs-mannheim"} <= set(inst)
    assert inst["hhn"]["requires_totp"] is True
    assert inst["uni-mannheim"]["requires_totp"] is False
    assert inst["hs-mannheim"]["requires_totp"] is False
    for i in inst.values():
        assert i.get("name"), i  # Anzeigename für die Auswahlliste


@pytest.mark.parametrize("query,expected", [
    ("heil", {"hhn"}),
    ("HHN", {"hhn"}),
    ("mannheim", {"uni-mannheim", "hs-mannheim"}),
    ("moodle", {"hs-mannheim"}),
    ("zzz", set()),
])
def test_setup_filter_like_autocomplete(hh: HhnHarness, query: str, expected: set[str]):
    """§3.2: Tippen filtert (case-insensitiv, Teilstring in Schlüssel, Name, Stadt oder LMS)."""
    r = hh.run("setup", "--list", "--filter", query, "--json")
    assert r.exit_code == 0, str(r)
    assert {i["key"] for i in json.loads(r.stdout)["instances"]} == expected


# ---------------------------------------------------------------- Erfolg (hhn mit TOTP)
def test_setup_hhn_success_stores_session_and_config(hh: HhnHarness):
    """§3.3/§3.4: Passwort + EIN TOTP über stdin -> verifizierter Login, Session gespeichert,
    config.toml enthält Instanz + Benutzername (nicht geheim), sonst nichts Geheimes."""
    r = hh.setup(*HHN, "--username", USERNAME, "--json", input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 0, str(r)
    data = r.json(strict=False)
    assert data["ok"] is True and data["instance"] == "hhn"
    assert len(hh.otp_posts()) == 1
    # Login bewiesen: Dashboard nach dem Callback geladen
    assert any(rq.query.get("baseClass", [""])[0].lower() == "ildashboardgui" for rq in hh.world.requests_to("ilias"))
    cfg = config_text(hh)
    assert 'instance = "hhn"' in cfg and USERNAME in cfg, cfg
    assert hh.world.ilias_base in cfg, "vorhandene Config-Werte (base_url) müssen erhalten bleiben"
    assert hh.run("status", *HHN).exit_code == 0
    assert_no_secret_leak(hh)


def test_setup_then_courses_without_new_2fa(hh: HhnHarness):
    """§4.2: Nach setup laufen courses/ls ohne erneute Eingabe und ohne Keycloak-Kontakt."""
    assert hh.setup(*HHN, "--username", USERNAME, input=f"{PASSWORD}\n{TOTP}\n").exit_code == 0
    kc = len(hh.world.requests_to("keycloak"))
    r = hh.run("courses", "--json")
    assert r.exit_code == 0, str(r)
    assert len(hh.world.requests_to("keycloak")) == kc


def test_setup_username_default_from_config(hh: HhnHarness):
    """§3.3 Schritt 2: Benutzername-Default aus vorheriger Config; ohne TTY reicht dann `--instance`."""
    assert hh.setup(*HHN, "--username", USERNAME, input=f"{PASSWORD}\n{TOTP}\n").exit_code == 0
    assert hh.run("logout", *HHN).exit_code == 0
    n = len(hh.password_posts())
    r = hh.setup(*HHN, input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 0, str(r)
    assert hh.password_posts()[n].form.get("username") == [USERNAME]


# ---------------------------------------------------------------- Fehler / Abbruch
def test_setup_wrong_password_exit1_no_retry(hh: HhnHarness):
    """§3.5: falsches Passwort -> klare Meldung, Exit 1, genau EIN Passwort-POST (keine Schleife, Konto-Sperre vermeiden)."""
    r = hh.setup(*HHN, "--username", USERNAME, input=f"falsch-{PASSWORD}\n{TOTP}\n{TOTP}\n")
    assert r.exit_code == 1, str(r)
    assert len(hh.password_posts()) == 1
    assert "Passwort" in r.stderr or "Passwort" in r.stdout
    assert_nothing_stored(hh)


def test_setup_totp_retry_then_success(hh: HhnHarness):
    """§3.5: falscher Code -> erneute Abfrage im selben Keycloak-Ablauf; 3. Versuch richtig -> Exit 0."""
    r = hh.setup(*HHN, "--username", USERNAME, input=f"{PASSWORD}\n000000\n111111\n{TOTP}\n")
    assert r.exit_code == 0, str(r)
    assert len(hh.otp_posts()) == 3
    assert len(hh.password_posts()) == 1, "Passwort darf für einen neuen Code-Versuch nicht neu gesendet werden"


def test_setup_totp_three_wrong_exit1(hh: HhnHarness):
    """§3.5: max. 3 Code-Versuche, danach Exit 1, nichts gespeichert, kein 4. POST."""
    r = hh.setup(*HHN, "--username", USERNAME, input=f"{PASSWORD}\n000000\n111111\n222222\n{TOTP}\n")
    assert r.exit_code == 1, str(r)
    assert len(hh.otp_posts()) == 3
    assert_nothing_stored(hh)


def test_setup_eof_is_abort(hh: HhnHarness):
    """§3.5: stdin endet vor dem Passwort (wie Ctrl-D) -> Exit 1, nichts gespeichert, kein Keycloak-POST."""
    r = hh.setup(*HHN, "--username", USERNAME, input="")
    assert r.exit_code == 1, str(r)
    assert hh.kc_posts() == []
    assert "Traceback" not in r.stderr
    assert_nothing_stored(hh)


def test_setup_eof_at_totp_is_abort(hh: HhnHarness):
    """§3.5: Abbruch beim Code -> Exit 1, nichts gespeichert, keine Config-Änderung mit Benutzername."""
    r = hh.setup(*HHN, "--username", USERNAME, input=f"{PASSWORD}\n")
    assert r.exit_code == 1, str(r)
    assert_nothing_stored(hh)
    assert USERNAME not in config_text(hh), "bei Abbruch darf auch die Config nicht geändert werden"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT-Test nur POSIX")
def test_setup_sigint_is_abort(hh: HhnHarness):
    """§3.5: Ctrl-C (SIGINT) während der Passwort-Abfrage -> Exit 1, kein Traceback, nichts gespeichert."""
    proc = subprocess.Popen(
        [ilias_executable(), "setup", *HHN, "--username", USERNAME],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=hh.env(), cwd=hh.cwd, start_new_session=True,
    )
    time.sleep(2.0)  # Prompt erreicht (stdin bleibt offen)
    proc.send_signal(signal.SIGINT)
    try:
        out, err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("setup reagiert nicht auf SIGINT")
    assert proc.returncode == 1, (proc.returncode, out, err)
    assert "Traceback" not in err
    assert_nothing_stored(hh)


def test_setup_no_tty_without_instance_errors(hh: HhnHarness):
    """§3.6: kein TTY und keine Instanz -> Exit 1 mit Hinweis auf --instance/--username + stdin; kein Netz."""
    (hh.config_dir / "config.toml").write_text("", encoding="utf-8")
    r = hh.setup(input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 1, str(r)
    assert "--instance" in r.stderr + r.stdout
    assert hh.world.requests == []


def test_setup_no_tty_without_username_errors(hh: HhnHarness):
    """§3.6: kein TTY, Instanz da, aber weder --username noch gespeicherter Benutzername -> Exit 1 mit Hinweis."""
    r = hh.setup(*HHN, input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 1, str(r)
    assert "--username" in r.stderr + r.stdout
    assert hh.kc_posts() == []


def test_setup_unknown_instance_exit1(hh: HhnHarness):
    r = hh.setup("--instance", "gibt-es-nicht", "--username", USERNAME, input=f"{PASSWORD}\n")
    assert r.exit_code == 1, str(r)
    assert hh.world.requests == []


# ---------------------------------------------------------------- Instanz ohne 2FA
def test_setup_uni_mannheim_no_totp(tmp_path):
    """§3.3 Schritt 4: Instanz ohne 2FA (uni-mannheim, SAML) fragt KEINEN Code ab."""
    shib = pytest.importorskip("acceptance.fake_shibboleth")
    world = shib.FakeShibWorld(username=USERNAME, password=PASSWORD).start()
    try:
        h = HhnHarness(tmp_path, world)
        (h.config_dir / "config.toml").write_text(
            f'[instances.uni-mannheim]\nbase_url = "{world.ilias_base}"\n', encoding="utf-8")
        r = h.setup("--instance", "uni-mannheim", "--username", USERNAME, input=f"{PASSWORD}\n")
        assert r.exit_code == 0, str(r)
        assert "TOTP" not in r.stdout + r.stderr and "Einmalcode" not in r.stdout + r.stderr
        assert h.run("status", "--instance", "uni-mannheim").exit_code == 0
        assert USERNAME in (h.config_dir / "config.toml").read_text(encoding="utf-8")
        assert not h.net_log.exists() or not h.net_log.read_text().strip()
    finally:
        world.stop()


def test_env_password_never_used(hh: HhnHarness):
    """A1: setup liest KEIN Passwort aus Umgebungsvariablen (nur verdeckter Prompt bzw. stdin)."""
    base_env = hh.env
    hh.env = lambda: {**base_env(), "ILIAS_PASSWORD": PASSWORD, "HHN_ILIAS_PASSWORD": PASSWORD}  # type: ignore[method-assign]
    r = hh.run("setup", *HHN, "--username", USERNAME, input="")
    assert r.exit_code == 1, str(r)
    assert hh.kc_posts() == [], "Passwort wurde offenbar aus der Umgebung gelesen"
