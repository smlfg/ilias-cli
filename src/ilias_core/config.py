"""Konfiguration der ILIAS-CLI.

Geladen aus ``~/.config/ilias-cli/config.toml``. Der Pfad ist über die
Environment-Variable ``ILIAS_CLI_CONFIG`` überschreibbar (für Tests).
Nichts ist hart kodiert außer den HHN-Defaults.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_CLIENT_ID = "iliashhn"
CONFIG_ENV_VAR = "ILIAS_CLI_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ilias-cli" / "config.toml"


@dataclass
class Config:
    """Konfiguration für eine ILIAS-Instanz."""

    base_url: str = DEFAULT_BASE_URL
    client_id: str = DEFAULT_CLIENT_ID
    config_path: Path = field(default_factory=lambda: DEFAULT_CONFIG_PATH)

    @property
    def session_path(self) -> Path:
        """Pfad der Session-Datei (neben der Config-Datei)."""
        return self.config_path.parent / "session.json"


def default_config_path() -> Path:
    """Config-Pfad: Env-Variable hat Vorrang, sonst Default."""
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env)
    # GLUE (Vergleichs-Repo, INTERFACE.md §4): Verzeichnis-Variable ILIAS_CLI_CONFIG_DIR unterstützen
    env_dir = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if env_dir:
        return Path(env_dir) / "config.toml"
    return DEFAULT_CONFIG_PATH


def load_config(path: Path | str | None = None) -> Config:
    """Config laden. Fehlende Datei/Keys -> HHN-Defaults.

    ``path=None`` -> Pfad aus ``ILIAS_CLI_CONFIG`` bzw. Default.
    """
    if path is None:
        config_path = default_config_path()
    else:
        config_path = Path(path)

    data: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)

    return Config(
        base_url=data.get("base_url", DEFAULT_BASE_URL),
        client_id=data.get("client_id", DEFAULT_CLIENT_ID),
        config_path=config_path,
    )
