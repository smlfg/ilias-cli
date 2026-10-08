"""Konfiguration und Instanz-Profile (N6, N7).

Quellen und Vorrang (höher schlägt niedriger):
  1. CLI-Argumente (``--instance``, ``--base-url``)
  2. ``config.toml`` im Konfigurationsverzeichnis
  3. eingebautes Instanz-Profil (z. B. ``hs-mannheim``)
  4. Defaults (HHN ILIAS)

Konfigurationsverzeichnis: ``$ILIAS_CLI_CONFIG_DIR`` sonst ``~/.config/ilias-cli``.
Geschrieben wird nur in dieses Verzeichnis, nie ins Arbeitsverzeichnis.
"""

from __future__ import annotations

import os
import re
import tomllib
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ILIAS_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_ILIAS_CLIENT_ID = "iliashhn"

BUILTIN_INSTANCES: dict[str, dict[str, str]] = {
    "hs-mannheim": {
        "base_url": "https://moodle.hs-mannheim.de",
        "lms": "moodle",
    },
    "hhn": {
        "base_url": DEFAULT_ILIAS_BASE_URL,
        "lms": "ilias",
        "client_id": DEFAULT_ILIAS_CLIENT_ID,
    },
}


def config_dir() -> Path:
    """Konfigurationsverzeichnis (INTERFACE.md §4)."""
    override = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~")) / ".config" / "ilias-cli"


def _host_of(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.hostname or base_url


def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "default"


@dataclass
class InstanceConfig:
    instance: str
    lms: str
    base_url: str
    client_id: str | None
    config_dir: Path

    @property
    def is_moodle(self) -> bool:
        return self.lms == "moodle"

    @property
    def store_key(self) -> str:
        return _safe_key(self.instance)


def load_config(
    instance: str | None = None,
    base_url: str | None = None,
    *,
    config_path: Path | None = None,
) -> InstanceConfig:
    """Konfiguration auflösen (siehe Modul-Docstring)."""
    cdir = config_dir()
    path = config_path if config_path is not None else (cdir / "config.toml")

    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}

    profile_name = instance or data.get("instance")
    profile: dict[str, str] = BUILTIN_INSTANCES.get(profile_name, {}) if profile_name else {}

    lms = str(data.get("lms") or profile.get("lms") or "ilias").lower()
    resolved_base = (
        base_url
        or data.get("base_url")
        or profile.get("base_url")
        or DEFAULT_ILIAS_BASE_URL
    ).rstrip("/")
    client_id = data.get("client_id") or profile.get("client_id") or DEFAULT_ILIAS_CLIENT_ID

    name = profile_name or _host_of(resolved_base)
    return InstanceConfig(
        instance=name,
        lms=lms,
        base_url=resolved_base,
        client_id=client_id,
        config_dir=cdir,
    )
