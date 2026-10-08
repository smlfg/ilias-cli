"""A1: Das Passwort darf niemals in Logs, Output oder Exceptions auftauchen."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from typer.testing import CliRunner

from ilias_cli.main import app
from ilias_core.auth.flow import login
from ilias_core.config import Config
from ilias_core.errors import AuthenticationError
from ilias_core.models import LoginResult
from ilias_core.session.manager import SessionManager
from ilias_core.session.store import InMemorySessionStore

from conftest import (
    BASE_URL,
    VALID_OTP,
    VALID_PASSWORD,
    VALID_USERNAME,
    make_handler,
)

SECRET_PASSWORD = "Sup3rS3cret!Password#2026"
runner = CliRunner()


def test_password_not_in_logs(success_client, caplog):
    client, _ = success_client
    with caplog.at_level(logging.DEBUG):
        login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
        with pytest.raises(AuthenticationError):
            login(BASE_URL, VALID_USERNAME, SECRET_PASSWORD, VALID_OTP, client=client)

    assert VALID_PASSWORD not in caplog.text
    assert SECRET_PASSWORD not in caplog.text


def test_password_not_in_exception(success_client):
    client, _ = success_client
    with pytest.raises(AuthenticationError) as exc_info:
        login(BASE_URL, VALID_USERNAME, SECRET_PASSWORD, VALID_OTP, client=client)
    assert SECRET_PASSWORD not in str(exc_info.value)
    assert SECRET_PASSWORD not in repr(exc_info.value)


def test_password_not_in_public_dict():
    result = LoginResult(cookies={"PHPSESSID": "x"}, final_url="https://x")
    assert SECRET_PASSWORD not in json.dumps(result.public_dict())


def test_password_not_stored_in_session(success_client):
    client, _ = success_client
    result = login(BASE_URL, VALID_USERNAME, VALID_PASSWORD, VALID_OTP, client=client)
    store = InMemorySessionStore()
    config = Config(base_url=BASE_URL, client_id="iliashhn")
    manager = SessionManager(config, store=store)
    manager.save(result, username=VALID_USERNAME)

    data = store.load()
    raw = json.dumps(
        {
            "base_url": data.base_url,
            "client_id": data.client_id,
            "cookies": data.cookies,
            "username": data.username,
        }
    )
    assert VALID_PASSWORD not in raw
    assert SECRET_PASSWORD not in raw


def test_password_not_in_cli_output(cli_env, html, monkeypatch, capsys):
    handler, _ = make_handler(html)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr("ilias_cli.commands.login.create_client", lambda: client)

    result = runner.invoke(
        app,
        ["login", "--username", VALID_USERNAME, "--json"],
        input=f"{VALID_PASSWORD}\n{VALID_OTP}\n",
    )
    captured = capsys.readouterr()
    assert VALID_PASSWORD not in captured.out
    assert VALID_PASSWORD not in captured.err
    assert result.exit_code == 0
