"""Moodle-Login/Status/Logout gegen lokalen Fake-Moodle-Server."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tests.acceptance.leak_check import find_secret_in_paths, find_secret_in_text

from .conftest import MoodleHarness
from .fake_moodle import PASSWORD, SITENAME, USERNAME


def test_help_lists_commands(h: MoodleHarness):
    r = h.run("--help")
    assert r.exit_code == 0
    for cmd in ("login", "status", "logout"):
        assert cmd in r.stdout


def test_login_success(h: MoodleHarness):
    r = h.login()
    assert r.exit_code == 0, r.stderr
    assert SITENAME in r.stdout
    token = h.world.last_token
    assert token, "Fake-Moodle hat keinen Token ausgegeben"
    assert any(token in v for v in h.keyring_data().values()), "Token nicht im Keyring gespeichert"
    assert PASSWORD not in r.stdout and PASSWORD not in r.stderr
    for f in h.written_files():
        assert PASSWORD.encode() not in f.read_bytes()


def test_login_json_shape(h: MoodleHarness):
    r = h.login("--json")
    assert r.exit_code == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert data["lms"] == "moodle"
    assert data["instance"] == "hs-mannheim"
    assert data["sitename"] == SITENAME
    assert data["username"] == USERNAME
    assert data["fullname"]
    assert "T" in data["timestamp"] and ("+" in data["timestamp"] or data["timestamp"].endswith("Z"))
    assert PASSWORD not in r.stdout
    assert h.world.last_token not in r.stdout


def test_login_wrong_password_exit_1(h: MoodleHarness):
    r = h.login(password="falsch")
    assert r.exit_code == 1, r.stderr
    assert not any(h.world.last_token and h.world.last_token in v for v in h.keyring_data().values())
    assert not h.keyring_data()


def test_login_server_error_exit_4(h: MoodleHarness):
    h.world.token_mode = "error500"
    r = h.login()
    assert r.exit_code == 4


def test_login_unexpected_html_exit_5(h: MoodleHarness):
    h.world.token_mode = "html"
    r = h.login()
    assert r.exit_code == 5


def test_login_network_error_exit_4(h: MoodleHarness, tmp_path):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    (h.config_dir / "config.toml").write_text(
        f'base_url = "http://127.0.0.1:{port}"\nlms = "moodle"\ninstance = "hs-mannheim"\n', encoding="utf-8")
    r = h.login()
    assert r.exit_code == 4


def test_status_ok(h: MoodleHarness):
    assert h.login().exit_code == 0
    r = h.run("status")
    assert r.exit_code == 0
    assert SITENAME in r.stdout


def test_status_json(h: MoodleHarness):
    h.login()
    r = h.run("status", "--json")
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True and data["sitename"] == SITENAME
    assert h.world.last_token not in r.stdout + r.stderr


def test_status_invalid_token_exit_3(h: MoodleHarness):
    h.login()
    h.world.invalidate_tokens()
    r = h.run("status")
    assert r.exit_code == 3
    r = h.run("status", "--json")
    assert r.exit_code == 3
    data = json.loads(r.stdout)
    assert data["ok"] is False


def test_status_without_token_exit_2(h: MoodleHarness):
    r = h.run("status")
    assert r.exit_code == 2
    r = h.run("status", "--json")
    assert r.exit_code == 2
    assert json.loads(r.stdout)["ok"] is False


def test_status_unexpected_html_exit_5(h: MoodleHarness):
    h.login()
    h.world.rest_mode = "html"
    assert h.run("status").exit_code == 5


def test_status_server_error_exit_4(h: MoodleHarness):
    h.login()
    h.world.rest_mode = "error500"
    assert h.run("status").exit_code == 4


def test_logout_removes_token(h: MoodleHarness):
    h.login()
    assert h.keyring_data()
    r = h.run("logout", "--json")
    assert r.exit_code == 0
    assert json.loads(r.stdout)["ok"] is True
    assert not h.keyring_data()
    assert h.run("status").exit_code == 2


def test_logout_without_session_exit_0(h: MoodleHarness):
    r = h.run("logout")
    assert r.exit_code == 0


def test_token_file_fallback_0600(tmp_path, world):
    h = MoodleHarness(tmp_path, world, keyring_mode="none")
    h.write_config()
    r = h.login()
    assert r.exit_code == 0, r.stderr
    files = list((h.config_dir).glob("moodle-token-*"))
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert files[0].read_text().strip() == h.world.last_token
    h.run("logout")
    assert h.run("status").exit_code == 2
    assert not list(h.config_dir.glob("moodle-token-*"))


def test_no_secret_leak(h: MoodleHarness):
    h.login()
    h.run("status")
    h.run("logout")
    for secret in (PASSWORD,):
        assert not find_secret_in_text(secret, h.all_output())
        hits = find_secret_in_paths(secret, h.written_files())
        assert not hits, hits
    token = h.world.last_token
    assert token
    for r in h.runs:
        assert not find_secret_in_text(token, r.stdout)
        assert not find_secret_in_text(token, r.stderr)
    for f in h.written_files():
        if f == h.keyring_file:
            continue
        assert not find_secret_in_text(token, f.read_bytes())
