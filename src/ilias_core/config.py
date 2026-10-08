"""Configuration management for ILIAS CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w


@dataclass
class Config:
    """Configuration for ILIAS connection."""

    base_url: str = "https://ilias.hs-heilbronn.de"
    client_id: str = "iliashhn"
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "ilias-cli")
    session_store: str = "auto"  # auto, keyring, file
    timeout: float = 30.0
    user_agent: str = "ilias-cli/0.1.0"

    @property
    def openidconnect_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/openidconnect.php"

    @property
    def dashboard_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/ilias.php?baseClass=ilDashboardGUI"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def session_file(self) -> Path:
        return self.config_dir / "session.json"


DEFAULT_CONFIG = Config()


def get_config_path() -> Path:
    """Get config file path, respecting ILIAS_CLI_CONFIG_DIR env var."""
    env_dir = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if env_dir:
        return Path(env_dir) / "config.toml"
    return DEFAULT_CONFIG.config_file


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from TOML file, falling back to defaults."""
    if config_path is None:
        config_path = get_config_path()

    config = Config()

    if config_path.exists():
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        if "base_url" in data:
            config.base_url = data["base_url"]
        if "client_id" in data:
            config.client_id = data["client_id"]
        if "session_store" in data:
            config.session_store = data["session_store"]
        if "timeout" in data:
            config.timeout = float(data["timeout"])
        if "config_dir" in data:
            config.config_dir = Path(data["config_dir"]).expanduser()

    return config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration to TOML file."""
    if config_path is None:
        config_path = get_config_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "base_url": config.base_url,
        "client_id": config.client_id,
        "session_store": config.session_store,
        "timeout": config.timeout,
        "config_dir": str(config.config_dir),
    }

    with config_path.open("wb") as f:
        tomli_w.dump(data, f)


def ensure_config_dir(config: Config) -> None:
    """Ensure config directory exists with proper permissions."""
    config.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)