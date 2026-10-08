"""Integration #23 + #31: genau eine HTTP-Schicht (``Fetcher``) für `courses`/`ls`, plus Setup-Feinschliff.

- `courses`/`ls` schicken **keinen** zusätzlichen Vorab-Request zur Session-Prüfung
  (früher ``prepare_read`` aus #23: Kursliste vor jedem Befehl, nur ``login.php`` als
  abgelaufen erkannt).
- `setup --filter` gilt auch für die interaktive Auswahl; Enter bei mehreren Treffern
  fragt erneut; Netzwerk-Hinweis nennt die URL (und `--instance <key>`); ohne TTY keine
  getpass-Warnung, Passwort nie im Output.

Gegen die lokalen Fakes (127.0.0.1), nur synthetische Daten.
"""

from __future__ import annotations

import importlib
import json

import pytest
from acceptance.leak_check import find_secret_in_text
from hhn.conftest import (
    PASSWORD,
    TOTP,
    USERNAME,
    HhnHarness,
    assert_no_external_network,
)
from hhn.fake_hhn import HhnWorld

from ilias_cli import prompts
from ilias_core import setup as setup_core
from ilias_core.errors import AbortedError

cli_main = importlib.import_module("ilias_cli.main")  # Modul, nicht die gleichnamige Funktion
MEMBERSHIP = "ilmembershipoverviewgui"


@pytest.fixture
def hworld():
    w = HhnWorld(username=USERNAME, password=PASSWORD, totp=TOTP).start()
    yield w
    w.stop()


@pytest.fixture
def hh(tmp_path, hworld) -> HhnHarness:
    harness = HhnHarness(tmp_path, hworld)
    yield harness
    assert_no_external_network(harness)


@pytest.fixture
def logged_in(hh: HhnHarness) -> HhnHarness:
    r = hh.login()
    assert r.exit_code == 0, str(r)
    return hh


def _ilias_gets_since(h: HhnHarness, since: int) -> list:
    return [r for r in h.world.requests[since:] if r.server == "ilias"]


def _is_membership(rec) -> bool:
    return rec.query.get("baseClass", [""])[0].lower() == MEMBERSHIP


# ---------------------------------------------------------------- eine HTTP-Schicht
def test_courses_sends_exactly_one_request(logged_in: HhnHarness):
    n = len(logged_in.world.requests)
    r = logged_in.run("courses", "--json")
    assert r.exit_code == 0, str(r)
    new = _ilias_gets_since(logged_in, n)
    assert [(x.method, _is_membership(x)) for x in new] == [("GET", True)], [(x.method, x.path, x.query) for x in new]


def test_ls_has_no_extra_pre_request(logged_in: HhnHarness):
    """ls = 1x Kursliste (Kursauflösung) + 1x Kursseite bei --depth 2; kein Vorab-Request."""
    n = len(logged_in.world.requests)
    r = logged_in.run("ls", "900101", "--depth", "2", "--json")
    assert r.exit_code == 0, str(r)
    new = _ilias_gets_since(logged_in, n)
    assert all(x.method == "GET" for x in new)
    assert sum(1 for x in new if _is_membership(x)) == 1, [(x.path, x.query) for x in new]
    assert len(new) == 2, [(x.path, x.query) for x in new]
    assert logged_in.world.requested_refs(n) == [900101]


def test_expired_session_one_request_exit3(logged_in: HhnHarness):
    logged_in.world.expire_all_sessions()
    n = len(logged_in.world.requests)
    kc = len(logged_in.world.requests_to("keycloak"))
    for args in (("courses",), ("ls", "900101")):
        m = len(logged_in.world.requests)
        r = logged_in.run(*args, "--json")
        assert r.exit_code == 3, str(r)
        assert len(_ilias_gets_since(logged_in, m)) == 1
    assert len(logged_in.world.requests_to("keycloak")) == kc
    assert len(logged_in.world.requests) - n == 2


# ---------------------------------------------------------------- setup ohne TTY
def test_setup_no_tty_password_from_stdin_without_getpass_warning(hh: HhnHarness):
    r = hh.setup("--instance", "hhn", "--username", USERNAME, "--json", input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 0, str(r)
    out = r.stdout + r.stderr
    assert "may be echoed" not in out and "GetPassWarning" not in out, r.stderr
    assert not find_secret_in_text(PASSWORD, out)
    assert not find_secret_in_text(TOTP, out)
    assert json.loads(r.stdout)["ok"] is True


def test_setup_no_tty_eof_at_password_is_abort(hh: HhnHarness):
    r = hh.setup("--instance", "hhn", "--username", USERNAME, "--json", input="")
    assert r.exit_code == 1, str(r)
    assert json.loads(r.stdout)["error"]["code"] == "aborted"
    assert "may be echoed" not in r.stderr and "Traceback" not in r.stderr
    assert hh.kc_posts() == []


def test_network_hint_names_url_and_instance(hh: HhnHarness):
    hh.world.stop_ilias()
    r = hh.setup("--instance", "hhn", "--username", USERNAME, "--json", input=f"{PASSWORD}\n{TOTP}\n")
    assert r.exit_code == 4, str(r)
    hint = json.loads(r.stdout)["error"]["hint"] or ""
    assert hh.world.ilias_base in hint, hint
    assert "--instance hhn" in hint, hint


# ---------------------------------------------------------------- interaktive Auswahl
class _Tty:
    def isatty(self) -> bool:
        return True


def test_setup_filter_applies_to_interactive_picker(monkeypatch):
    seen: list[list[str]] = []

    def fake_choose(infos):
        seen.append([info.key for info in infos])
        raise AbortedError()

    monkeypatch.setattr(cli_main.sys, "stdin", _Tty())
    monkeypatch.setattr(cli_main.prompts, "choose_instance", fake_choose)
    with pytest.raises(AbortedError):
        cli_main._setup_run(None, None, False, False, "heil")
    assert seen == [["hhn"]]


def test_picker_enter_with_multiple_matches_reprompts(monkeypatch):
    answers = iter(["", "mannheim", "", "2"])
    prompts_seen: list[str] = []

    def fake_prompt(text, *a, **k):
        prompts_seen.append(text)
        return next(answers)

    monkeypatch.setattr(prompts.typer, "prompt", fake_prompt)
    assert prompts.choose_instance(setup_core.all_instances()) == "hs-mannheim"
    assert len(prompts_seen) == 4  # Enter wählte nie still den ersten Treffer


def test_picker_invalid_number_reprompts(monkeypatch):
    answers = iter(["9", "1"])
    monkeypatch.setattr(prompts.typer, "prompt", lambda *a, **k: next(answers))
    assert prompts.choose_instance(setup_core.all_instances()) == "hhn"


def test_picker_empty_filter_result_errors_with_list_hint():
    from ilias_core.errors import ConfigError

    with pytest.raises(ConfigError) as excinfo:
        prompts.choose_instance([])
    assert "ilias setup --list" in (excinfo.value.hint or "")
