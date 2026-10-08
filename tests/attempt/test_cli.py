"""End-to-End-Tests der CLI (Exit-Codes, JSON, keine Cookies im Output)."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core.config import load_config
from ilias_core.session import SessionStore

from helpers import (
    mock_dashboard_for_status,
    mock_expired_session,
    mock_successful_login,
    mock_wrong_password,
)

runner = CliRunner()


def _save_session(config_dir, cookies=None):
    store = SessionStore(load_config())
    store.save(cookies or {"PHPSESSID": "secret-session", "ilClientId": "iliashhn"})
    return store


def test_help_commands_work():
    for args in (["--help"], ["login", "--help"], ["status", "--help"], ["logout", "--help"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output


def test_status_logged_in_json(config_dir, memory_keyring):
    _save_session(config_dir)
    with respx.mock(assert_all_called=False) as router:
        mock_dashboard_for_status(router)
        result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["authenticated"] is True
    assert "PHPSESSID" not in result.stdout
    assert "secret-session" not in result.stdout


def test_status_without_session_exit_2(config_dir, memory_keyring):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2
    assert "Nicht eingeloggt" in result.output


def test_status_expired_exit_3(config_dir, memory_keyring):
    _save_session(config_dir)
    with respx.mock(assert_all_called=False) as router:
        mock_expired_session(router)
        result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 3


def test_login_success_json(config_dir, memory_keyring, monkeypatch):
    monkeypatch.setattr("ilias_cli.prompts.ask_username", lambda: "student")
    monkeypatch.setattr("ilias_cli.prompts.ask_password", lambda: "geheim")
    monkeypatch.setattr("ilias_cli.prompts.ask_totp", lambda: "123456")
    with respx.mock(assert_all_called=True) as router:
        mock_successful_login(router)
        result = runner.invoke(app, ["login", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["authenticated"] is True
    assert "PHPSESSID" not in result.stdout
    assert SessionStore(load_config()).load()["PHPSESSID"] == "super-secret-session"


def test_login_wrong_password_exit_1(config_dir, memory_keyring, monkeypatch):
    monkeypatch.setattr("ilias_cli.prompts.ask_username", lambda: "student")
    monkeypatch.setattr("ilias_cli.prompts.ask_password", lambda: "geheim")
    monkeypatch.setattr("ilias_cli.prompts.ask_totp", lambda: "123456")
    with respx.mock(assert_all_called=False) as router:
        mock_wrong_password(router)
        result = runner.invoke(app, ["login", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_logout_clears_session_json(config_dir, memory_keyring):
    _save_session(config_dir)
    result = runner.invoke(app, ["logout", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "session_removed": True}
    assert SessionStore(load_config()).load() is None


def test_cli_password_not_in_output(config_dir, memory_keyring, monkeypatch, caplog):
    password = "NochGeheimer-987"
    monkeypatch.setattr("ilias_cli.prompts.ask_username", lambda: "student")
    monkeypatch.setattr("ilias_cli.prompts.ask_password", lambda: password)
    monkeypatch.setattr("ilias_cli.prompts.ask_totp", lambda: "123456")

    with respx.mock(assert_all_called=False) as router:
        mock_wrong_password(router)
        result = runner.invoke(app, ["login"])

    assert result.exit_code == 1
    assert password not in result.output
    assert password not in caplog.text
