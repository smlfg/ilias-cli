"""Tests for config module."""

import tempfile
from pathlib import Path

import pytest

from ilias_core.config import Config, load_config, save_config, get_config_path


def test_default_config() -> None:
    """Test default configuration values."""
    config = Config()
    assert config.base_url == "https://ilias.hs-heilbronn.de"
    assert config.client_id == "iliashhn"
    assert config.session_store == "auto"
    assert config.timeout == 30.0


def test_config_properties() -> None:
    """Test computed properties."""
    config = Config(base_url="https://example.com", client_id="test")
    assert config.openidconnect_url == "https://example.com/openidconnect.php"
    assert config.dashboard_url == "https://example.com/ilias.php?baseClass=ilDashboardGUI"


def test_load_config_defaults(temp_config_dir: Path) -> None:
    """Test loading config when file doesn't exist."""
    config_path = temp_config_dir / "config.toml"
    config = load_config(config_path)
    assert config.base_url == "https://ilias.hs-heilbronn.de"
    assert config.client_id == "iliashhn"


def test_load_config_from_file(temp_config_dir: Path) -> None:
    """Test loading config from TOML file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("""
base_url = "https://custom.ilias.de"
client_id = "custom"
session_store = "file"
timeout = 60.0
""")
    config = load_config(config_path)
    assert config.base_url == "https://custom.ilias.de"
    assert config.client_id == "custom"
    assert config.session_store == "file"
    assert config.timeout == 60.0


def test_save_config(temp_config_dir: Path) -> None:
    """Test saving config to TOML file."""
    config_path = temp_config_dir / "config.toml"
    config = Config(
        base_url="https://save.test.de",
        client_id="savetest",
        session_store="keyring",
        timeout=45.0,
        config_dir=temp_config_dir,
    )
    save_config(config, config_path)

    loaded = load_config(config_path)
    assert loaded.base_url == "https://save.test.de"
    assert loaded.client_id == "savetest"
    assert loaded.session_store == "keyring"
    assert loaded.timeout == 45.0


def test_get_config_path_env_override(monkeypatch: pytest.MonkeyPatch, temp_config_dir: Path) -> None:
    """Test config path respects environment variable."""
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(temp_config_dir))
    path = get_config_path()
    assert path == temp_config_dir / "config.toml"