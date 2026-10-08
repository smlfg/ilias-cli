"""Konfiguration: Profile, config.toml, Pfade."""

from __future__ import annotations

import os
from pathlib import Path

from .models import ResolvedConfig

BUILTIN_INSTANCES: dict[str, dict[str, str]] = {
    "hs-mannheim": {
        "base_url": "https://moodle.hs-mannheim.de",
        "lms": "moodle",
    },
}

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_LMS = "ilias"


def config_dir() -> Path:
    override = os.environ.get("ILIAS_CLI_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "ilias-cli"


def _load_toml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    # Minimaler TOML-Parser: tomllib (3.11+) wenn verfügbar.
    try:
        import tomllib  # type: ignore

        return tomllib.loads(text)
    except Exception:
        pass
    # Sehr kleiner Fallback für flache key = "value"-Dateien + [instances.x].
    data: dict = {}
    instances: dict[str, dict] = {}
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith("instances."):
                name = section.split(".", 1)[1].strip().strip('"').strip("'")
                current = {}
                instances[name] = current
            else:
                current = None
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Inline-Kommentare grob entfernen (nur wenn # mit Space).
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        target = current if current is not None else data
        target[k] = v
    if instances:
        data["instances"] = instances
    return data


def load_raw_config() -> dict:
    path = config_dir() / "config.toml"
    data = _load_toml(path)
    if not isinstance(data, dict):
        return {}
    return data


def resolve(
    instance_cli: str | None = None,
    base_url_cli: str | None = None,
    lms_cli: str | None = None,
) -> ResolvedConfig:
    raw = load_raw_config()
    instance = instance_cli or raw.get("instance") or None
    if instance is not None:
        instance = str(instance).strip() or None

    instances = raw.get("instances")
    if not isinstance(instances, dict):
        instances = {}
    inst_cfg: dict = {}
    if instance and isinstance(instances.get(instance), dict):
        inst_cfg = instances[instance]

    builtin = BUILTIN_INSTANCES.get(instance, {}) if instance else {}

    lms = (
        (lms_cli or "").strip()
        or str(inst_cfg.get("lms", "")).strip()
        or str(raw.get("lms", "")).strip()
        or str(builtin.get("lms", "")).strip()
        or DEFAULT_LMS
    )
    lms = lms.lower()

    base_url = (
        (base_url_cli or "").strip()
        or str(inst_cfg.get("base_url", "")).strip()
        or str(raw.get("base_url", "")).strip()
        or str(builtin.get("base_url", "")).strip()
        or DEFAULT_BASE_URL
    )
    base_url = base_url.rstrip("/")

    return ResolvedConfig(instance=instance, lms=lms, base_url=base_url)


def instance_key(instance: str | None) -> str:
    return instance or "default"
