"""Moodle-Login-Tests (nur localhost-Fake-Server, keine echten Requests)."""

from __future__ import annotations

import json
import stat
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from .conftest import (
    FULLNAME,
    PASSWORD,
    SITENAME,
    TOKEN,
    USERID,
    USERNAME,
    Harness,
    file_mode,
)
from .fake_moodle import FakeMoodle

sys_path_check = None


def _last_json_stdout(r) -> dict:
    return json.loads(r.stdout.strip())


def _checked_at_ok(payload: dict) -> None:
    assert "checked_at" in payload, f"checked_at fehlt: {payload}"
    dt = datetime.fromisoformat(payload["checked_at"])
    assert dt.tzinfo is not None, f"checked_at ohne Zeitzone: {payload['checked_at']}"
    berlin = ZoneInfo("Europe/Berlin")
    # Offset muss zu Europe/Berlin passen (Sommer/Winter automatisch).
    expected_offset = dt.astimezone(berlin).utcoffset()
    assert dt.utcoffset() == expected_offset, f"checked_at nicht Europe/Berlin: {payload['checked_at']}"


# ---------------------------------------------------------------- Erfolg
def test_login_success(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    assert FULLNAME in r.stdout or USERNAME in r.stdout, str(r)
    assert SITENAME in r.stdout, str(r)
    assert TOKEN not in r.stdout + r.stderr, "Token in Ausgabe!"
    assert PASSWORD not in r.stdout + r.stderr, "Passwort in Ausgabe!"
    # Token gespeichert (Keyring oder Datei).
    assert h.files_containing(TOKEN), "Token wurde nirgends gespeichert"


def test_login_success_json_shape(h: Harness):
    r = h.login("--json")
    assert r.exit_code == 0, str(r)
    data = _last_json_stdout(r)
    assert data["status"] == "ok"
    assert data["username"] == USERNAME
    assert data["fullname"] == FULLNAME
    assert data["sitename"] == SITENAME
    assert data["userid"] == USERID
    assert data["lms"] == "moodle"
    _checked_at_ok(data)
    assert "token" not in json.dumps(data).lower(), "Token im JSON!"
    assert PASSWORD not in r.stdout + r.stderr


def test_login_posts_service_and_user_agent(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    posts = h.world.requests_to("/login/token.php")
    assert posts, "token.php nie aufgerufen (falsche base_url?)"
    form = {k: v[0] for k, v in posts[0].form.items()}
    assert form.get("service") == "moodle_mobile_app", f"service fehlt: {form}"
    assert form.get("username") == [USERNAME][0] or form.get("username") == USERNAME
    uas = {rr.headers.get("User-Agent", "") for rr in h.world.requests}
    assert uas and all(ua.startswith("ilias-cli/") for ua in uas), uas
    # site_info wurde zur Verifikation aufgerufen.
    assert h.world.requests_to("/webservice/rest/server.php"), "site_info nicht verifiziert"


# ---------------------------------------------------------------- Fehlerfälle
def test_wrong_password_exit_1_and_no_session(h: Harness):
    r = h.login(password="falsches-Passwort-123-xyz")
    assert r.exit_code in (1, 2), str(r)
    assert r.exit_code != 0
    assert not h.files_containing(TOKEN), "Token trotz falschem Passwort gespeichert"
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_wrong_password_json(h: Harness):
    r = h.login("--json", password="falsches-Passwort-123-xyz")
    assert r.exit_code in (1, 2), str(r)
    if r.stdout.strip():
        data = r.json(strict=False)
        assert isinstance(data, dict)
        assert TOKEN not in r.stdout + r.stderr


def test_server_error_500_exit_4(h: Harness):
    h.world.token_mode = "error500"
    r = h.login()
    assert r.exit_code == 4, str(r)
    assert not h.files_containing(TOKEN)


def test_server_error_500_json(h: Harness):
    h.world.token_mode = "error500"
    r = h.login("--json")
    assert r.exit_code == 4, str(r)
    if r.stdout.strip():
        r.json()


def test_unexpected_html_exit_5(h: Harness):
    h.world.token_mode = "html"
    r = h.login()
    assert r.exit_code == 5, str(r)
    assert not h.files_containing(TOKEN)


def test_unexpected_html_json(h: Harness):
    h.world.token_mode = "html"
    r = h.login("--json")
    assert r.exit_code == 5, str(r)
    if r.stdout.strip():
        r.json()


def test_siteinfo_failure_no_token_stored(h: Harness):
    """Token ok, aber site_info kaputt -> kein Erfolg, kein gespeichertes Token."""
    h.world.siteinfo_mode = "html"
    r = h.login()
    assert r.exit_code == 5, str(r)
    assert not h.files_containing(TOKEN), "Token ohne Verifikation gespeichert!"


def test_network_error_exit_4(h: Harness, tmp_path):
    from .conftest import free_port

    h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
    r = h.login()
    assert r.exit_code == 4, str(r)


# ---------------------------------------------------------------- status
def test_status_ok(h: Harness):
    assert h.login().exit_code == 0
    r = h.run("status")
    assert r.exit_code == 0, str(r)
    assert USERNAME in r.stdout or FULLNAME in r.stdout, str(r)
    assert TOKEN not in r.stdout + r.stderr


def test_status_json_ok_no_token(h: Harness):
    assert h.login().exit_code == 0
    r = h.run("status", "--json")
    assert r.exit_code == 0, str(r)
    data = _last_json_stdout(r)
    assert data["status"] == "ok"
    assert data["username"] == USERNAME
    assert data["sitename"] == SITENAME
    _checked_at_ok(data)
    assert "token" not in json.dumps(data).lower()


def test_status_without_token_exit_2(h: Harness):
    r = h.run("status")
    assert r.exit_code == 2, str(r)


def test_status_without_token_json(h: Harness):
    r = h.run("status", "--json")
    assert r.exit_code == 2, str(r)
    if r.stdout.strip():
        data = r.json()
        assert isinstance(data, dict)
        _checked_at_ok(data)


def test_status_invalid_token_exit_3(h: Harness):
    assert h.login().exit_code == 0
    h.world.siteinfo_mode = "invalidtoken"
    r = h.run("status")
    assert r.exit_code == 3, str(r)


def test_status_invalid_token_json(h: Harness):
    assert h.login().exit_code == 0
    h.world.siteinfo_mode = "invalidtoken"
    r = h.run("status", "--json")
    assert r.exit_code == 3, str(r)
    if r.stdout.strip():
        r.json()


def test_status_server_error_exit_4(h: Harness):
    assert h.login().exit_code == 0
    h.world.siteinfo_mode = "error500"
    r = h.run("status")
    assert r.exit_code == 4, str(r)


# ---------------------------------------------------------------- logout
def test_logout_removes_token(h: Harness):
    assert h.login().exit_code == 0
    assert h.files_containing(TOKEN)
    r = h.run("logout", "--json")
    assert r.exit_code == 0, str(r)
    assert isinstance(r.json(), dict), str(r)
    assert h.files_containing(TOKEN) == [], "Token nach logout noch gespeichert"
    s = h.run("status")
    assert s.exit_code == 2, str(s)


def test_logout_without_session_ok(h: Harness):
    r = h.run("logout")
    assert r.exit_code == 0, str(r)
    r2 = h.run("logout", "--json")
    assert r2.exit_code == 0, str(r2)
    r2.json()


def test_logout_json_shape(h: Harness):
    assert h.login().exit_code == 0
    r = h.run("logout", "--json")
    assert r.exit_code == 0, str(r)
    data = r.json()
    assert data["status"] == "ok"
    _checked_at_ok(data)
    assert TOKEN not in r.stdout + r.stderr


# ---------------------------------------------------------------- Secrets & Rechte
def _stored_token_files(h: Harness) -> list[Path]:
    return h.files_containing(TOKEN)


def test_password_never_in_output_or_files(h: Harness):
    h.login()
    h.run("status")
    h.run("status", "--json")
    assert PASSWORD not in h.all_output(), "Passwort in Ausgabe!"
    # URL-/Base64-Varianten grob mitprüfen.
    import base64
    import urllib.parse

    variants = [
        PASSWORD,
        urllib.parse.quote(PASSWORD),
        base64.b64encode(PASSWORD.encode()).decode(),
    ]
    for p in h.written_files():
        try:
            content = p.read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        for v in variants:
            assert v not in content, f"Passwort in Datei {p}"


@pytest.mark.parametrize("scenario", ["success", "wrong_password", "server_error", "garbage_html", "network_error"])
def test_password_never_leaks_all_scenarios(h: Harness, scenario: str):
    from .conftest import free_port

    if scenario == "wrong_password":
        h.login(password="falsches-Pw-xyz-123")
    elif scenario == "server_error":
        h.world.token_mode = "error500"
        h.login()
    elif scenario == "garbage_html":
        h.world.token_mode = "html"
        h.login()
    elif scenario == "network_error":
        h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
        h.login()
    else:
        h.login()
        h.run("status")
    assert PASSWORD not in h.all_output(), f"Passwort in Ausgabe ({scenario})!"
    for p in h.written_files():
        try:
            data = p.read_bytes()
        except OSError:
            continue
        assert PASSWORD.encode() not in data, f"Passwort in Datei {p} ({scenario})"


def test_token_never_in_output_and_only_in_store(h: Harness):
    r = h.login("--json")
    assert r.exit_code == 0, str(r)
    s = h.run("status", "--json")
    assert s.exit_code == 0, str(s)
    assert TOKEN not in h.all_output(), "Token in stdout/stderr!"
    allowed = set(_stored_token_files(h))
    assert allowed, "Token nirgends gespeichert"
    for p in h.written_files():
        if p in allowed:
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        assert TOKEN.encode() not in data, f"Token außerhalb des Stores in {p}"


def test_token_file_permissions_0600(h: Harness):
    h.keyring_mode = "none"
    r = h.login()
    assert r.exit_code == 0, str(r)
    candidates = [p for p in h.written_files() if p != h.keyring_file]
    assert candidates, "Kein Datei-Fallback geschrieben"
    for p in candidates:
        if p.name == "net-blocked.log":
            continue
        assert file_mode(p) == 0o600, f"{p} hat {oct(file_mode(p))}, erwartet 0600"
    # status funktioniert mit Datei-Fallback.
    s = h.run("status")
    assert s.exit_code == 0, str(s)


def test_keyring_or_0600_file(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    artifacts = h.files_containing(TOKEN)
    assert artifacts, "Token nirgends gespeichert"
    for p in artifacts:
        assert h.cwd not in p.parents, f"Token im Arbeitsverzeichnis: {p}"
        if p == h.keyring_file:
            continue
        import os

        if os.name != "nt":
            assert file_mode(p) == 0o600, f"{p}: {oct(file_mode(p))}"


# ---------------------------------------------------------------- CLI-Vertrag
def test_no_password_flag(h: Harness):
    r = h.run("login", "--help")
    assert r.exit_code == 0, str(r)
    assert "--password" not in r.stdout, "login bietet --password an"


@pytest.mark.parametrize("cmd", ["login", "status", "logout"])
def test_each_command_has_json_flag(h: Harness, cmd: str):
    r = h.run(cmd, "--help")
    assert r.exit_code == 0, str(r)
    assert "--json" in r.stdout, str(r)


def test_help_lists_commands(h: Harness):
    r = h.run("--help")
    assert r.exit_code == 0, str(r)
    for cmd in ("login", "status", "logout"):
        assert cmd in r.stdout


# ---------------------------------------------------------------- Instanzen & Config
def test_instance_via_cli_flag(h: Harness, tmp_path):
    # Config ohne Instanz, Auswahl nur über --instance + --base-url.
    h.config_dir.joinpath("config.toml").write_text(
        f'base_url = "{h.world.base_url}"\n', encoding="utf-8"
    )
    r = h.run("login", "--instance", "hs-mannheim", "--base-url", h.world.base_url, input=f"{USERNAME}\n{PASSWORD}\n")
    assert r.exit_code == 0, str(r)


def test_instance_via_config_file(h: Harness):
    # Bereits Standard: instance=hs-mannheim in config.toml.
    r = h.login()
    assert r.exit_code == 0, str(r)


def test_base_url_overridable_via_flag(h: Harness):
    from .conftest import free_port

    # Falsche URL in Config, richtige per Flag -> muss trotzdem gehen.
    h.write_config(base_url=f"http://127.0.0.1:{free_port()}", instance="hs-mannheim")
    r = h.run(
        "login",
        "--instance",
        "hs-mannheim",
        "--base-url",
        h.world.base_url,
        input=f"{USERNAME}\n{PASSWORD}\n",
    )
    assert r.exit_code == 0, str(r)


def test_builtin_hs_mannheim_profile():
    from ilias_core.config import BUILTIN_INSTANCES

    assert "hs-mannheim" in BUILTIN_INSTANCES
    assert BUILTIN_INSTANCES["hs-mannheim"]["base_url"] == "https://moodle.hs-mannheim.de"
    assert BUILTIN_INSTANCES["hs-mannheim"]["lms"] == "moodle"


def test_resolve_defaults_to_ilias_without_instance(tmp_path, monkeypatch):
    import os

    from ilias_core import config as config_mod

    d = tmp_path / "empty-config"
    d.mkdir()
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(d))
    resolved = config_mod.resolve()
    assert resolved.lms == "ilias"
    assert resolved.base_url == "https://ilias.hs-heilbronn.de"
