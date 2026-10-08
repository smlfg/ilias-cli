"""Konfiguration: config.toml mit Instance-Profilen, Umgebungsvariablen, Defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InstanceProfile:
    """Ein einzelnes Instanz-Profil (z. B. hs-mannheim, hhn-ilias)."""

    name: str
    base_url: str
    lms: str = "ilias"  # "ilias" | "moodle"
    client_id: str | None = None  # nur für ILIAS
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.lms not in ("ilias", "moodle"):
            raise ValueError(f"Unbekanntes LMS: {self.lms}")


@dataclass
class Config:
    """Gesamte Konfiguration mit Defaults und Instanz-Profilen."""

    default_instance: str = "default"
    instances: dict[str, InstanceProfile] = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: Path | None = None) -> Config:
        """Lädt Konfiguration aus Datei und Umgebungsvariablen."""
        config = cls()

        # Built-in Profile
        config.instances["hs-mannheim"] = InstanceProfile(
            name="hs-mannheim",
            base_url="https://moodle.hs-mannheim.de",
            lms="moodle",
        )
        config.instances["hhn-ilias"] = InstanceProfile(
            name="hhn-ilias",
            base_url="https://ilias.hs-heilbronn.de",
            lms="ilias",
            client_id="iliashhn",
        )

        # Config-Datei laden
        config_file = cls._find_config_file(config_dir)
        if config_file and config_file.exists():
            file_config = cls._parse_config_file(config_file)
            config._merge_file_config(file_config)

        # Environment Overrides
        config._apply_env_overrides()

        return config

    @staticmethod
    def _find_config_file(config_dir: Path | None = None) -> Path | None:
        """Findet die config.toml Datei."""
        if config_dir:
            return config_dir / "config.toml"

        # $ILIAS_CLI_CONFIG_DIR
        env_dir = os.environ.get("ILIAS_CLI_CONFIG_DIR")
        if env_dir:
            return Path(env_dir) / "config.toml"

        # ~/.config/ilias-cli/config.toml
        home = Path.home()
        return home / ".config" / "ilias-cli" / "config.toml"

    @staticmethod
    def _parse_config_file(path: Path) -> dict[str, Any]:
        with path.open("rb") as f:
            return tomllib.load(f)

    def _merge_file_config(self, data: dict[str, Any]) -> None:
        if "default_instance" in data:
            self.default_instance = data["default_instance"]

        if "instances" in data:
            for name, inst_data in data["instances"].items():
                if isinstance(inst_data, dict):
                    self.instances[name] = InstanceProfile(
                        name=name,
                        base_url=inst_data.get("base_url", ""),
                        lms=inst_data.get("lms", "ilias"),
                        client_id=inst_data.get("client_id"),
                        extra=inst_data.get("extra", {}),
                    )

    def _apply_env_overrides(self) -> None:
        """Umgebungsvariablen überschreiben Instanz-Profile."""
        # ILIAS_BASE_URL, ILIAS_CLIENT_ID für Default-Instanz
        if base_url := os.environ.get("ILIAS_BASE_URL"):
            if self.default_instance in self.instances:
                self.instances[self.default_instance].base_url = base_url
            else:
                self.instances[self.default_instance] = InstanceProfile(
                    name=self.default_instance, base_url=base_url
                )

        if client_id := os.environ.get("ILIAS_CLIENT_ID"):
            if self.default_instance in self.instances:
                self.instances[self.default_instance].client_id = client_id

    def get_instance(self, name: str | None = None) -> InstanceProfile:
        """Holt ein Instanz-Profil, nutzt Default falls None."""
        instance_name = name or self.default_instance
        if instance_name not in self.instances:
            raise ValueError(f"Instanz-Profil '{instance_name}' nicht gefunden")
        return self.instances[instance_name]

    def resolve_base_url(self, instance_name: str | None, base_url_override: str | None = None) -> str:
        """Ermittelt die finale Base-URL (Override > Profil > Default)."""
        if base_url_override:
            return base_url_override.rstrip("/")
        instance = self.get_instance(instance_name)
        return instance.base_url.rstrip("/")


def get_config_dir(config_dir: Path | None = None) -> Path:
    """Ermittelt das Konfigurationsverzeichnis."""
    if config_dir:
        return config_dir

    env_dir = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)

    return Path.home() / ".config" / "ilias-cli"