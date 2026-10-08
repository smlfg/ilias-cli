"""Konfiguration und Instanz-Profile (INTERFACE.md §4, N6/N7).

Datei: `$ILIAS_CLI_CONFIG_DIR/config.toml`, sonst `~/.config/ilias-cli/config.toml`.

Beispiel (HS Mannheim, eingebauter Profile-Key `hs-mannheim`):

    instance = "hs-mannheim"

    [instances.hs-mannheim]
    base_url = "https://moodle.hs-mannheim.de"   # überschreibt das eingebaute Profil
    lms = "moodle"

Die alte flache Form bleibt gültig und beschreibt die Default-Instanz (ILIAS/HHN):

    base_url = "https://ilias.hs-heilbronn.de"
    client_id = "iliashhn"

Basis-URLs sind nie hart kodiert: eingebautes Profil < config.toml.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError

CONFIG_DIR_ENV = "ILIAS_CLI_CONFIG_DIR"
CONFIG_FILE_NAME = "config.toml"
DEFAULT_INSTANCE = "hhn"
BACKEND_ILIAS = "ilias"
BACKEND_MOODLE = "moodle"
KNOWN_BACKENDS = (BACKEND_ILIAS, BACKEND_MOODLE)

# Eingebaute Profile (N7: nur Startwerte, in config.toml überschreibbar)
BUILTIN_INSTANCES: dict[str, dict[str, Any]] = {
    "hhn": {
        "lms": BACKEND_ILIAS,
        "base_url": "https://ilias.hs-heilbronn.de",
        "client_id": "iliashhn",
        "label": "ILIAS Hochschule Heilbronn",
    },
    "hs-mannheim": {
        "lms": BACKEND_MOODLE,
        "base_url": "https://moodle.hs-mannheim.de",
        "label": "Moodle Hochschule Mannheim",
    },
}

_INSTANCE_KEYS = ("lms", "base_url", "client_id", "label")


@dataclass(frozen=True)
class Instance:
    """Eine konkrete Zielinstanz (Backend + Basis-URL)."""

    key: str
    lms: str
    base_url: str
    client_id: str | None = None
    label: str | None = None
    source: str = "builtin"

    def with_overrides(self, **kwargs: Any) -> Instance:
        return replace(self, **kwargs)

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "ilias-cli"


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def read_config() -> dict[str, Any]:
    """Liest config.toml; fehlende Datei -> leere Config (Defaults greifen)."""
    path = config_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"Konfiguration {path} nicht lesbar: {exc.strerror or exc}") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Konfiguration {path} ist ungültiges TOML: {exc}") from None
    return data


def _instance_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k in _INSTANCE_KEYS and isinstance(v, str) and v.strip()}


def default_instance_key(config: dict[str, Any] | None = None) -> str:
    """Welche Instanz ohne `--instance` verwendet wird."""
    config = read_config() if config is None else config
    key = config.get("instance")
    if isinstance(key, str) and key.strip():
        return key.strip()
    if _instance_fields(config) or any(k in config for k in ("instances",)):
        return config.get("default_instance", DEFAULT_INSTANCE) or DEFAULT_INSTANCE
    return DEFAULT_INSTANCE


def known_instances(config: dict[str, Any] | None = None) -> list[str]:
    config = read_config() if config is None else config
    keys = list(BUILTIN_INSTANCES)
    for key in config.get("instances", {}) or {}:
        if key not in keys:
            keys.append(key)
    return keys


def load_instance(key: str | None = None, config: dict[str, Any] | None = None) -> Instance:
    """Baut das Instanz-Profil: eingebautes Profil, dann config.toml, dann Defaults."""
    config = read_config() if config is None else config
    key = (key or default_instance_key(config)).strip()
    if not key:
        raise ConfigError("Kein Instanz-Key angegeben.")

    data: dict[str, Any] = dict(BUILTIN_INSTANCES.get(key, {}))
    source = "config" if key in BUILTIN_INSTANCES else "user"
    # flache Config-Felder gelten für die Default-Instanz
    if key == DEFAULT_INSTANCE:
        data.update(_instance_fields(config))
        if data != BUILTIN_INSTANCES.get(key, {}):
            source = "config"
    instances = config.get("instances") or {}
    entry = instances.get(key)
    if entry is not None:
        if not isinstance(entry, dict):
            raise ConfigError(f"[instances.{key}] muss eine Tabelle sein.")
        data.update(_instance_fields(entry))
        source = "config"

    lms = str(data.get("lms") or BACKEND_ILIAS).strip().lower()
    if lms not in KNOWN_BACKENDS:
        raise ConfigError(
            f"Unbekanntes Backend {lms!r} für Instanz {key!r} (bekannt: {', '.join(KNOWN_BACKENDS)})."
        )
    base_url = str(data.get("base_url") or "").strip()
    if not base_url:
        if key in BUILTIN_INSTANCES:
            raise ConfigError(f"Instanz {key!r} hat keine Basis-URL.")
        raise ConfigError(
            f"Instanz {key!r} ist unbekannt. Bekannte Instanzen: {', '.join(known_instances(config))}. "
            f"Bitte [instances.{key}] mit base_url und lms in {config_path()} anlegen."
        )
    return Instance(
        key=key,
        lms=lms,
        base_url=base_url,
        client_id=(str(data["client_id"]).strip() if data.get("client_id") else None),
        label=(str(data["label"]).strip() if data.get("label") else None),
        source=source,
    )
