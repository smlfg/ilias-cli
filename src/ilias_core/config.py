from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_CLIENT_ID = "iliashhn"

ENV_CONFIG = "ILIAS_CLI_CONFIG"
ENV_CONFIG_DIR = "ILIAS_CLI_CONFIG_DIR"


@dataclass(frozen=True)
class Config:
    base_url: str = DEFAULT_BASE_URL
    client_id: str = DEFAULT_CLIENT_ID


def config_dir() -> Path:
    override = os.environ.get(ENV_CONFIG_DIR)
    if override:
        return Path(override)
    return Path.home() / ".config" / "ilias-cli"


def config_path() -> Path:
    override = os.environ.get(ENV_CONFIG)
    if override:
        return Path(override)
    return config_dir() / "config.toml"


def load_config(path: Path | None = None) -> Config:
    p = path or config_path()
    if not p.exists():
        return Config()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Config(
        base_url=str(data.get("base_url", DEFAULT_BASE_URL)).rstrip("/"),
        client_id=str(data.get("client_id", DEFAULT_CLIENT_ID)),
    )
