"""Konfiguration: Datei, Instanz-Profile, Defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import CliError

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_CLIENT_ID = "iliashhn"
DEFAULT_LMS = "ilias"

BUILTIN_INSTANCES: dict[str, dict[str, str]] = {
    "hs-mannheim": {
        "base_url": "https://moodle.hs-mannheim.de",
        "lms": "moodle",
    },
}


@dataclass(frozen=True)
class Config:
    base_url: str
    client_id: str
    lms: str
    instance: str | None


def config_dir() -> Path:
    override = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "ilias-cli"


def config_path() -> Path:
    return config_dir() / "config.toml"


def load_config_file() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CliError(f"Konfigurationsdatei ungültig: {exc}", exit_code=1) from exc


def resolve_config(instance_flag: str | None = None) -> Config:
    cfg = load_config_file()
    instance = instance_flag or cfg.get("instance")
    known = instance in BUILTIN_INSTANCES if instance else False
    profile = BUILTIN_INSTANCES.get(instance, {}) if instance else {}
    if instance and not known and not cfg.get("base_url"):
        raise CliError(f"Unbekannte Instanz: {instance}", exit_code=1)
    base_url = cfg.get("base_url") or profile.get("base_url") or DEFAULT_BASE_URL
    client_id = cfg.get("client_id") or profile.get("client_id") or DEFAULT_CLIENT_ID
    lms = cfg.get("lms") or profile.get("lms") or DEFAULT_LMS
    return Config(base_url=base_url.rstrip("/"), client_id=client_id, lms=lms, instance=instance)
