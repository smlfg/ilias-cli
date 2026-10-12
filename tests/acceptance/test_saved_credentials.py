"""Opt-in `ilias login --save-password`: Benutzername + Passwort im Schlüsselbund.

Owner-Entscheid (A1, Komfort > Sicherheit): das Passwort darf **nur** im OS-Schlüsselbund
liegen und nur nach `--save-password`; nie in Dateien, Ausgaben oder ohne Opt-in.
Das TOTP wird weiterhin jedes Mal abgefragt und nie gespeichert.
"""

from __future__ import annotations

from .conftest import PASSWORD, TOTP, USERNAME, Harness
from .leak_check import find_secret_in_paths, find_secret_in_text


def _save(h: Harness):
    r = h.login("--save-password")
    assert r.exit_code == 0, str(r)
    assert "gespeichert" in r.stderr
    return r


def test_saved_credentials_only_ask_totp(h: Harness):
    _save(h)
    h.run("logout")
    r = h.run("login", input=f"{TOTP}\n")
    assert r.exit_code == 0, str(r)
    assert "Passwort" not in r.stderr and "Benutzername" not in r.stderr
    assert USERNAME in r.stderr  # Hinweis, wessen Daten benutzt werden
    assert h.run("status").exit_code == 0


def test_password_only_in_keyring_never_in_output(h: Harness):
    _save(h)
    h.run("login", input=f"{TOTP}\n")
    assert not find_secret_in_text(PASSWORD, h.all_output())
    assert find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd]) == []
    assert find_secret_in_paths(PASSWORD, [h.keyring_file.parent]) == [h.keyring_file]


def test_without_keyring_nothing_is_saved(h: Harness):
    h.keyring_mode = "none"
    r = h.login("--save-password")
    assert r.exit_code == 0, str(r)
    assert "nicht gespeichert" in r.stderr
    assert find_secret_in_paths(PASSWORD, [h.home, h.config_dir, h.cwd, h.keyring_file.parent]) == []


def test_rejected_saved_password_is_forgotten(h: Harness):
    _save(h)
    h.world.password = PASSWORD + "-neu"
    r = h.run("login", input=f"{TOTP}\n")
    assert r.exit_code != 0, str(r)
    assert "gelöscht" in r.stderr
    assert find_secret_in_paths(PASSWORD, [h.keyring_file.parent]) == []
    # danach wieder normale Abfrage
    r = h.login(password=PASSWORD + "-neu")
    assert r.exit_code == 0, str(r)


def test_wrong_totp_keeps_saved_password(h: Harness):
    _save(h)
    r = h.run("login", input="000000\n")
    assert r.exit_code != 0, str(r)
    assert find_secret_in_paths(PASSWORD, [h.keyring_file.parent]) == [h.keyring_file]


def test_logout_forget_removes_credentials(h: Harness):
    _save(h)
    r = h.run("logout", "--forget")
    assert r.exit_code == 0, str(r)
    assert "Zugangsdaten gelöscht" in r.stderr
    assert find_secret_in_paths(PASSWORD, [h.keyring_file.parent]) == []
    r = h.login()  # fragt wieder alles ab
    assert r.exit_code == 0, str(r)
