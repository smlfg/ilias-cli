"""Tests für den Moodle-Login (login/status/logout) gegen den lokalen Fake-Server.

Prüft Exit-Codes (INTERFACE.md §3 / Task), Autorisierungsfehler, Fehlerfälle,
JSON-Formen und die Secret-Hygiene (A1/A4).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from .conftest import PASSWORD, SUPPORT_DIR, USERNAME, Harness, file_mode, free_port

TOKEN_ENDPOINT = "/login/token.php"
REST_ENDPOINT = "/webservice/rest/server.php"


def login_token_requests(h: Harness):
    return h.world.requests_to(TOKEN_ENDPOINT)


def site_info_requests(h: Harness):
    return h.world.requests_to(REST_ENDPOINT)


def token_store_files(h: Harness):
    """Dateien, die den Token enthalten dürfen (Keyring oder 0600-Fallback)."""
    allowed = {h.keyring_file}
    return [p for p in h.files_containing(h.world.token) if p not in allowed]


# ---------------------------------------------------------------- CLI-Grundlagen
def test_help_lists_commands(h: Harness):
    r = h.run("--help")
    assert r.exit_code == 0, str(r)
    for cmd in ("login", "status", "logout"):
        assert cmd in r.stdout


@pytest.mark.parametrize("cmd", ["login", "status", "logout"])
def test_each_command_has_json_flag(h: Harness, cmd: str):
    r = h.run(cmd, "--help")
    assert r.exit_code == 0, str(r)
    assert "--json" in r.stdout, str(r)


def test_login_has_no_password_flag(h: Harness):
    """A1: kein --password-Flag."""
    r = h.run("login", "--help")
    assert r.exit_code == 0, str(r)
    assert "--password" not in r.stdout, str(r)


# ---------------------------------------------------------------- Login
def test_login_success_and_status(h: Harness):
    r = h.login()
    assert r.exit_code == 0, str(r)
    posts = login_token_requests(h)
    assert posts, "login/token.php wurde nie aufgerufen"
    assert posts[0].first("service") == "moodle_mobile_app"
    assert posts[0].first("username") == USERNAME

    s = h.run("status")
    assert s.exit_code == 0, str(s)


def test_login_verifies_site_info_before_store(h: Harness):
    """Vor dem Speichern wird core_webservice_get_site_info aufgerufen."""
    r = h.login()
    assert r.exit_code == 0, str(r)
    infos = site_info_requests(h)
    assert infos, "core_webservice_get_site_info wurde nicht aufgerufen"
    assert infos[0].first("wsfunction") == "core_webservice_get_site_info"
    assert infos[0].first("moodlewsrestformat") == "json"


def test_login_invalid_token_is_not_stored(h: Harness):
    """Verifikation schlägt fehl -> kein Token gespeichert."""
    h.world.site_info_mode = "invalid_token"
    r = h.login()
    assert r.exit_code != 0, str(r)
    assert token_store_files(h) == []
    assert h.run("status").exit_code == 2


def test_login_wrong_password(h: Harness):
    r = h.login(password="falsches-Passwort-123")
    assert r.exit_code in {1, 2}, str(r)
    assert r.exit_code != 0
    assert h.run("status").exit_code == 2


def test_login_server_error_exit_4(h: Harness):
    h.world.token_mode = "server_error"
    r = h.login()
    assert r.exit_code == 4, str(r)
    assert h.run("status").exit_code == 2


def test_login_unexpected_html_exit_5(h: Harness):
    h.world.token_mode = "html"
    r = h.login()
    assert r.exit_code == 5, str(r)
    assert h.run("status").exit_code == 2


def test_login_network_error_exit_4(h: Harness):
    h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
    r = h.login()
    assert r.exit_code == 4, str(r)


def test_user_agent(h: Harness):
    assert h.login().exit_code == 0
    agents = {r.headers.get("User-Agent", "") for r in h.world.requests}
    assert agents and all(a.startswith("ilias-cli/") for a in agents), agents


# ---------------------------------------------------------------- status
def test_status_without_token_exit_2(h: Harness):
    r = h.run("status")
    assert r.exit_code == 2, str(r)


def test_status_without_token_json(h: Harness):
    r = h.run("status", "--json")
    assert r.exit_code == 2, str(r)
    assert r.json()["exit_code"] == 2


def test_status_invalid_token_exit_3(h: Harness):
    assert h.login().exit_code == 0
    h.world.site_info_mode = "invalid_token"
    r = h.run("status")
    assert r.exit_code == 3, str(r)


def test_status_invalid_token_json_exit_3(h: Harness):
    assert h.login().exit_code == 0
    h.world.site_info_mode = "invalid_token"
    r = h.run("status", "--json")
    assert r.exit_code == 3, str(r)
    assert r.json()["errorcode"] == "invalidtoken"


def test_status_server_error_exit_4(h: Harness):
    assert h.login().exit_code == 0
    h.world.site_info_mode = "server_error"
    assert h.run("status").exit_code == 4


def test_status_unexpected_html_exit_5(h: Harness):
    assert h.login().exit_code == 0
    h.world.site_info_mode = "html"
    assert h.run("status").exit_code == 5


def test_status_network_error_exit_4(h: Harness):
    assert h.login().exit_code == 0
    h.world.stop()
    assert h.run("status").exit_code == 4


# ---------------------------------------------------------------- logout
def test_logout_removes_token(h: Harness):
    assert h.login().exit_code == 0
    r = h.run("logout", "--json")
    assert r.exit_code == 0, str(r)
    assert r.json()["removed"] is True
    assert token_store_files(h) == []
    assert h.run("status").exit_code == 2


def test_logout_without_token_ok(h: Harness):
    r = h.run("logout", "--json")
    assert r.exit_code == 0, str(r)
    assert r.json()["removed"] is False


# ---------------------------------------------------------------- JSON-Formen
def _assert_iso_berlin(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() in (3600, 7200), value


def test_json_shapes(h: Harness):
    login = h.login("--json")
    assert login.exit_code == 0, str(login)
    data = login.json()
    for key in ("lms", "instance", "base_url", "username", "fullname", "sitename", "logged_in_at"):
        assert key in data, data
    assert data["lms"] == "moodle"
    assert data["username"] == USERNAME
    assert data["sitename"] == h.world.sitename
    assert data["fullname"] == h.world.fullname
    _assert_iso_berlin(data["logged_in_at"])

    status = h.run("status", "--json")
    assert status.exit_code == 0
    sdata = status.json()
    assert sdata["valid"] is True
    assert sdata["username"] == USERNAME
    _assert_iso_berlin(sdata["checked_at"])

    logout = h.run("logout", "--json")
    assert logout.exit_code == 0
    ldata = logout.json()
    assert {"lms", "instance", "base_url", "removed", "logged_out_at"}.issubset(ldata)
    _assert_iso_berlin(ldata["logged_out_at"])


# ---------------------------------------------------------------- Speicherung (A4)
def test_token_stored_in_keyring_or_0600_file(h: Harness):
    assert h.login().exit_code == 0
    assert h.files_containing(h.world.token), "Token nirgends gespeichert"
    for path in token_store_files(h):
        assert h.cwd not in path.parents
        if os.name != "nt":
            assert file_mode(path) == 0o600, f"{path} hat {oct(file_mode(path))}"


def test_token_file_fallback_0600_without_keyring(h: Harness):
    h.keyring_mode = "none"
    assert h.login().exit_code == 0
    artifact = h.files_containing(h.world.token)
    assert artifact, "Kein Datei-Fallback geschrieben"
    if os.name != "nt":
        for path in artifact:
            assert file_mode(path) == 0o600, f"{path} hat {oct(file_mode(path))}"
    assert h.run("status").exit_code == 0


# ---------------------------------------------------------------- Geheimnisse (A1/A4)
SCENARIOS = ["success", "wrong_password", "server_error", "html", "network_error"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_password_never_in_output_or_files(h: Harness, scenario: str):
    if scenario == "wrong_password":
        h.login(password=PASSWORD + "-x")
    elif scenario == "server_error":
        h.world.token_mode = "server_error"
        h.login()
    elif scenario == "html":
        h.world.token_mode = "html"
        h.login()
    elif scenario == "network_error":
        h.write_config(base_url=f"http://127.0.0.1:{free_port()}")
        h.login()
    else:
        h.login()
        h.run("status")
        h.run("logout")

    assert PASSWORD not in h.all_output(), "Passwort in Ausgabe!\n" + h.all_output()
    for path in h.written_files():
        assert PASSWORD.encode() not in path.read_bytes(), f"Passwort in {path}"


def test_token_never_in_output(h: Harness):
    """A4: Token wird nie gedruckt."""
    assert h.login().exit_code == 0
    assert h.run("status").exit_code == 0
    assert h.world.token not in h.all_output(), "Token in Ausgabe!\n" + h.all_output()


def test_token_only_in_store(h: Harness):
    assert h.login().exit_code == 0
    store_hits = h.files_containing(h.world.token)
    assert store_hits
    for path in store_hits:
        assert path == h.keyring_file or (h.config_dir in path.parents), path


# ---------------------------------------------------------------- Konfiguration
def test_lms_key_selects_moodle(h: Harness):
    """config/instance key `lms = "moodle"`."""
    h.write_config(instance=None, lms="moodle")
    assert h.login().exit_code == 0


def test_cli_instance_and_base_url_override(h: Harness):
    """--instance hs-mannheim + --base-url überschreiben die config.toml."""
    h.write_config(instance=None, base_url=f"http://127.0.0.1:{free_port()}", lms="moodle")
    r = h.login("--instance", "hs-mannheim", "--base-url", h.world.base_url)
    assert r.exit_code == 0, str(r)
    assert h.run("status", "--instance", "hs-mannheim", "--base-url", h.world.base_url).exit_code == 0


def test_builtin_profile_hs_mannheim(tmp_path):
    """Eingebautes Profil: hs-mannheim -> moodle, echte Basis-URL (nur Config, kein Request)."""
    from ilias_core.config import load_config

    cfg = load_config(instance="hs-mannheim", config_path=tmp_path / "missing.toml")
    assert cfg.lms == "moodle"
    assert cfg.base_url == "https://moodle.hs-mannheim.de"


def test_default_profile_is_ilias(tmp_path):
    from ilias_core.config import load_config

    cfg = load_config(config_path=tmp_path / "missing.toml")
    assert cfg.lms == "ilias"
    assert cfg.base_url == "https://ilias.hs-heilbronn.de"


def test_instance_section_overrides_flat_config(h: Harness):
    """[instances.<key>] base_url/lms gewinnt gegen die flachen Werte."""
    (h.config_dir / "config.toml").write_text(
        'instance = "hs-mannheim"\n'
        'lms = "ilias"\n'
        f'base_url = "http://127.0.0.1:{free_port()}"\n'
        "\n"
        "[instances.hs-mannheim]\n"
        'lms = "moodle"\n'
        f'base_url = "{h.world.base_url}"\n',
        encoding="utf-8",
    )
    r = h.login()
    assert r.exit_code == 0, str(r)
    assert h.run("status").exit_code == 0


def test_instance_section_without_builtin_profile(tmp_path):
    """Auch ohne eingebautes Profil greift [instances.<key>]."""
    from ilias_core.config import load_config

    path = tmp_path / "config.toml"
    path.write_text(
        'instance = "custom-moodle"\n'
        "[instances.custom-moodle]\n"
        'lms = "moodle"\n'
        'base_url = "http://127.0.0.1:12345"\n',
        encoding="utf-8",
    )
    cfg = load_config(config_path=path)
    assert cfg.lms == "moodle"
    assert cfg.base_url == "http://127.0.0.1:12345"


# ---------------------------------------------------------------- Sandbox
_SANDBOX_GETADDRINFO = "import socket\nsocket.getaddrinfo('sandbox-blocked.invalid', 443)\n"
_SANDBOX_CONNECT = (
    "import socket\n"
    "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "s.connect(('203.0.113.1', 443))\n"
)


def _run_sandboxed(script: str, net_log: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(SUPPORT_DIR),
            "ACCEPTANCE_SANDBOX": "1",
            "ACCEPTANCE_NET_LOG": str(net_log),
        }
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sandbox_blocks_non_loopback_dns(tmp_path):
    """sitecustomize verhindert DNS zu Nicht-Loopback und protokolliert es."""
    net_log = tmp_path / "net-blocked.log"
    proc = _run_sandboxed(_SANDBOX_GETADDRINFO, net_log)
    assert proc.returncode != 0, proc.stdout
    assert "sandbox" in proc.stderr
    assert "getaddrinfo sandbox-blocked.invalid" in net_log.read_text(encoding="utf-8")


def test_sandbox_blocks_non_loopback_connect(tmp_path):
    """sitecustomize blockiert TCP-Verbindungen zu Nicht-Loopback."""
    net_log = tmp_path / "net-blocked.log"
    proc = _run_sandboxed(_SANDBOX_CONNECT, net_log)
    assert proc.returncode != 0, proc.stdout
    assert "sandbox" in proc.stderr
    assert "connect 203.0.113.1:443" in net_log.read_text(encoding="utf-8")


def test_sandbox_allows_loopback(tmp_path):
    net_log = tmp_path / "net-blocked.log"
    script = "import socket\nprint(socket.getaddrinfo('127.0.0.1', 80)[0][4])\n"
    proc = _run_sandboxed(script, net_log)
    assert proc.returncode == 0, proc.stderr
    assert not net_log.exists()
