"""Konfiguration der ILIAS-CLI.

Gelesen wird ``~/.config/ilias-cli/config.toml`` (bzw. der über die
Umgebungsvariable ``ILIAS_CLI_CONFIG_DIR`` überschriebene Ordner). Nur die
HHN-Defaults sind hart kodiert, alles andere kommt aus der Datei.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_CLIENT_ID = "iliashhn"
ENV_CONFIG_DIR = "ILIAS_CLI_CONFIG_DIR"


def default_config_dir() -> Path:
    """Liefert das Konfigurationsverzeichnis (per Env überschreibbar)."""

    override = os.environ.get(ENV_CONFIG_DIR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "ilias-cli"


@dataclass(frozen=True)
class Config:
    """Aufgelöste Konfiguration."""

    base_url: str = DEFAULT_BASE_URL
    client_id: str = DEFAULT_CLIENT_ID
    config_dir: Path = field(default_factory=default_config_dir)

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def session_file(self) -> Path:
        return self.config_dir / "session.json"


def load_config(path: Path | str | None = None) -> Config:
    """Lädt die Konfiguration aus TOML und fällt auf die Defaults zurück."""

    if path is not None:
        config_dir = Path(path).expanduser()
    else:
        config_dir = default_config_dir()

    base_url = DEFAULT_BASE_URL
    client_id = DEFAULT_CLIENT_ID
    config_file = config_dir / "config.toml"

    if config_file.is_file():
        with config_file.open("rb") as handle:
            data = tomllib.load(handle)
        raw_base = data.get("base_url")
        if isinstance(raw_base, str) and raw_base.strip():
            base_url = raw_base.strip().rstrip("/")
        raw_client = data.get("client_id")
        if isinstance(raw_client, str) and raw_client.strip():
            client_id = raw_client.strip()

    return Config(base_url=base_url, client_id=client_id, config_dir=config_dir)
