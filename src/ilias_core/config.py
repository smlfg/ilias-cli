"""Config loading: ~/.config/ilias-cli/config.toml with base_url and client_id."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field

from ilias_core import DEFAULT_BASE_URL, DEFAULT_CLIENT_ID

CONFIG_ENV_VAR = "ILIAS_CLI_CONFIG"  # full path to config.toml (for tests)
CONFIG_DIR_ENV_VAR = "ILIAS_CLI_CONFIG_DIR"  # override config dir (for tests)
CONFIG_FILENAME = "config.toml"


def default_config_dir() -> str:
    override = os.environ.get(CONFIG_DIR_ENV_VAR)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".config", "ilias-cli")


def config_file_path(config_dir: str | None = None) -> str:
    if CONFIG_ENV_VAR in os.environ:
        return os.environ[CONFIG_ENV_VAR]
    base = config_dir or default_config_dir()
    return os.path.join(base, CONFIG_FILENAME)


@dataclass
class IliasConfig:
    base_url: str = DEFAULT_BASE_URL
    client_id: str = DEFAULT_CLIENT_ID
    config_dir: str = field(default_factory=default_config_dir)

    def dashboard_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/ilias.php?baseClass=ilDashboardGUI"

    def openidconnect_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/openidconnect.php"


def load_config(config_dir: str | None = None, path: str | None = None) -> IliasConfig:
    """Load config.toml. Only base_url/client_id have hardcoded HHN defaults."""
    resolved_dir = config_dir or default_config_dir()
    resolved_path = path or config_file_path(config_dir)
    base_url = DEFAULT_BASE_URL
    client_id = DEFAULT_CLIENT_ID
    if os.path.exists(resolved_path):
        with open(resolved_path, "rb") as f:
            data = tomllib.load(f)
        if isinstance(data.get("base_url"), str) and data["base_url"].strip():
            base_url = data["base_url"].strip().rstrip("/")
        if isinstance(data.get("client_id"), str) and data["client_id"].strip():
            client_id = data["client_id"].strip()
    return IliasConfig(base_url=base_url, client_id=client_id, config_dir=resolved_dir)
