"""Tests für die Config (Defaults, TOML, Env-Variable)."""

from __future__ import annotations

from pathlib import Path

from ilias_core.config import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    Config,
    load_config,
)


def test_defaults():
    config = Config()
    assert config.base_url == "https://ilias.hs-heilbronn.de"
    assert config.client_id == "iliashhn"


def test_load_missing_file_returns_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILIAS_CLI_CONFIG", str(tmp_path / "nonexistent.toml"))
    config = load_config()
    assert config.base_url == DEFAULT_BASE_URL
    assert config.client_id == DEFAULT_CLIENT_ID


def test_load_toml_values(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'base_url = "https://ilias.example.org"\nclient_id = "example"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ILIAS_CLI_CONFIG", str(config_file))
    config = load_config()
    assert config.base_url == "https://ilias.example.org"
    assert config.client_id == "example"


def test_explicit_path_overrides_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILIAS_CLI_CONFIG", str(tmp_path / "env.toml"))
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('base_url = "https://explicit.example"\n', encoding="utf-8")
    config = load_config(explicit)
    assert config.base_url == "https://explicit.example"
    assert config.client_id == DEFAULT_CLIENT_ID


def test_session_path_next_to_config(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("", encoding="utf-8")
    config = load_config(config_file)
    assert config.session_path == tmp_path / "session.json"
