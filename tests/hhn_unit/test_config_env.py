"""Basis-URL-Override aus ``ILIAS_CLI_BASE_URL`` (docs/UX.md, INTERFACE.md §4)."""

from __future__ import annotations

import pytest

from ilias_core.config import ENV_BASE_URL, load_config
from ilias_core.errors import ConfigError


def test_base_url_env_overrides_instance(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_BASE_URL, "http://127.0.0.1:1234/")
    config = load_config(tmp_path, instance="hhn")
    assert config.base_url == "http://127.0.0.1:1234"
    assert config.instance == "hhn"
    assert config.config_dir == tmp_path


def test_invalid_base_url_env_is_config_error(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_BASE_URL, "kein-url")
    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path, instance="hhn")
    assert ENV_BASE_URL in excinfo.value.message
    assert excinfo.value.hint


def test_empty_base_url_env_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_BASE_URL, "  ")
    config = load_config(tmp_path, instance="hhn")
    assert config.base_url == "https://ilias.hs-heilbronn.de"
