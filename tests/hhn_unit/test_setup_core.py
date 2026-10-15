"""Unit-Tests der reinen Setup-Kernfunktionen (Spec §3).

Kein Netzwerk, keine Fakes: nur die Funktionen aus `ilias_core.setup` und die
interaktive Auswahl (gleiche Filterfunktion wie `--list --filter`).
"""

from __future__ import annotations

import pytest

from ilias_cli import prompts
from ilias_core import setup as setup_core


@pytest.mark.parametrize(
    "query,expected",
    [
        ("heil", {"hhn"}),
        ("HHN", {"hhn"}),
        ("mannheim", {"uni-mannheim", "hs-mannheim"}),
        ("moodle", {"hs-mannheim"}),
        ("zzz", set()),
        ("", {"hhn", "uni-mannheim", "hs-mannheim"}),
    ],
)
def test_filter_instances(query: str, expected: set[str]):
    assert {info.key for info in setup_core.filter_instances(query)} == expected


def test_all_instances_have_metadata():
    infos = {info.key: info for info in setup_core.all_instances()}
    assert infos["hhn"].requires_totp is True
    assert infos["uni-mannheim"].requires_totp is False
    assert infos["hs-mannheim"].requires_totp is False
    for info in infos.values():
        assert info.name and info.city and info.lms and info.auth and info.base_url


def test_merge_config_text_preserves_other_values():
    existing = (
        'base_url = "https://example.invalid"\n'
        "client_id = \"C\"\n\n"
        "[instances.uni-mannheim]\n"
        'base_url = "https://other.invalid"\n'
    )
    merged = setup_core.merge_config_text(existing, "hhn", "student")
    assert merged.startswith('instance = "hhn"\n')
    assert "https://example.invalid" in merged
    assert "[instances.uni-mannheim]" in merged
    assert "https://other.invalid" in merged
    assert "[instances.hhn]" in merged
    assert 'username = "student"' in merged


def test_merge_config_text_replaces_instance_and_username():
    existing = 'instance = "uni-mannheim"\n\n[instances.hhn]\nusername = "alt"\n'
    merged = setup_core.merge_config_text(existing, "hhn", "neu")
    assert merged.count("instance = ") == 1
    assert 'instance = "hhn"' in merged
    assert 'username = "alt"' not in merged
    assert 'username = "neu"' in merged


def test_stored_username_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(setup_core.merge_config_text("", "hhn", "student"), encoding="utf-8")
    assert setup_core.stored_username("hhn", path) == "student"
    assert setup_core.stored_username("uni-mannheim", path) is None


def test_choose_instance_single():
    infos = setup_core.all_instances()
    assert prompts.choose_instance([infos[0]]) == "hhn"


def test_choose_instance_by_number(monkeypatch):
    infos = setup_core.all_instances()
    monkeypatch.setattr(prompts.typer, "prompt", lambda *a, **k: "2")
    assert prompts.choose_instance(infos) == "uni-mannheim"


def test_choose_instance_by_filter(monkeypatch):
    infos = setup_core.all_instances()
    monkeypatch.setattr(prompts.typer, "prompt", lambda *a, **k: "moodle")
    assert prompts.choose_instance(infos) == "hs-mannheim"


def test_choose_instance_retries_on_no_match(monkeypatch):
    infos = setup_core.all_instances()
    answers = iter(["zzz", "1"])
    monkeypatch.setattr(prompts.typer, "prompt", lambda *a, **k: next(answers))
    assert prompts.choose_instance(infos) == "hhn"
