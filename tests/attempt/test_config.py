"""Tests für das Laden der Konfiguration."""

from __future__ import annotations

from ilias_core.config import DEFAULT_BASE_URL, DEFAULT_CLIENT_ID, load_config


def test_defaults_without_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ILIAS_CLI_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    cfg = load_config()

    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.client_id == DEFAULT_CLIENT_ID
    assert cfg.config_dir == tmp_path / ".config" / "ilias-cli"


def test_config_file_is_read(config_dir):
    (config_dir / "config.toml").write_text(
        'base_url = "https://ilias.example.org/"\n'
        'client_id = "otherclient"\n',
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.base_url == "https://ilias.example.org"
    assert cfg.client_id == "otherclient"


def test_partial_config_file_keeps_defaults(config_dir):
    (config_dir / "config.toml").write_text(
        'client_id = "nurclient"\n', encoding="utf-8"
    )

    cfg = load_config()

    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.client_id == "nurclient"
