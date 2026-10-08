"""Erst-Einrichtung (`ilias setup`): Instanz-Metadaten, Filter und atomares Config-Merge.

Reine Kernfunktionen ohne Prompts und ohne Netzwerk:

- :func:`filter_instances` / :func:`list_instances` liefern die eingebauten
  Instanz-Metadaten (Spec §3.2), case-insensitive Teilstring über Schlüssel,
  Anzeigename, Stadt und LMS.
- :func:`stored_username` liest den gespeicherten Benutzernamen einer Instanz.
- :func:`merge_config` schreibt ``instance = "<key>"`` und
  ``[instances.<key>] username = "..."`` atomar in ``config.toml`` und behält
  alle anderen (auch unbekannten) Werte bei (Spec §3.4).
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AUTH_OIDC_KEYCLOAK, BUILTIN_INSTANCES, config_path


@dataclass(frozen=True)
class InstanceInfo:
    """Öffentliche Metadaten einer eingebauten Instanz (Spec §3.2)."""

    key: str
    name: str
    city: str
    lms: str
    auth: str
    requires_totp: bool
    base_url: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "city": self.city,
            "lms": self.lms,
            "auth": self.auth,
            "requires_totp": self.requires_totp,
            "base_url": self.base_url,
        }


def _info(key: str, profile) -> InstanceInfo:  # noqa: ANN001 - InstanceProfile
    return InstanceInfo(
        key=key,
        name=profile.display_name or profile.name,
        city=profile.city,
        lms=profile.lms,
        auth=profile.auth,
        # TOTP verlangt nur der OIDC/Keycloak-Login (an der HHN `hhn`, Spec §3.2).
        requires_totp=profile.auth == AUTH_OIDC_KEYCLOAK,
        base_url=profile.base_url,
    )


def all_instances() -> list[InstanceInfo]:
    """Alle eingebauten Instanzen in Register-Reihenfolge."""

    return [_info(key, profile) for key, profile in BUILTIN_INSTANCES.items()]


def filter_instances(text: str | None) -> list[InstanceInfo]:
    """Eingebaute Instanzen, deren Schlüssel/Name/Stadt/LMS ``text`` enthalten.

    Case-insensitiver Teilstring; leerer/fehlender Text liefert alle (Spec §3.2).
    """

    items = all_instances()
    needle = (text or "").strip().lower()
    if not needle:
        return items
    return [
        info
        for info in items
        if needle in info.key.lower()
        or needle in info.name.lower()
        or needle in info.city.lower()
        or needle in info.lms.lower()
    ]


# Alias mit sprechendem Namen für die CLI.
list_instances = filter_instances


def _read_toml(path: Path | None = None) -> dict[str, Any]:
    config_file = path or config_path()
    if not config_file.is_file():
        return {}
    try:
        with config_file.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def stored_username(key: str, path: Path | None = None) -> str | None:
    """Gespeicherter Benutzername aus ``[instances.<key>] username`` (sonst ``None``)."""

    tables = _read_toml(path).get("instances")
    if isinstance(tables, dict):
        table = tables.get(key)
        if isinstance(table, dict):
            value = table.get("username")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_TABLE_HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_INSTANCE_LINE = re.compile(r"^\s*instance\s*=")
_USERNAME_LINE = re.compile(r"^\s*username\s*=")


def merge_config_text(text: str, key: str, username: str) -> str:
    """``text`` um ``instance`` + ``[instances.<key>] username`` ergänzen.

    Rein textbasiert, damit alle übrigen Zeilen (base_url-Overrides, andere
    Instanzen, Kommentare) unverändert bleiben. Bestehende ``instance``- bzw.
    ``username``-Zeilen werden ersetzt, fehlende eingefügt.
    """

    lines = text.splitlines()

    # 1) Top-Level `instance = "..."` (nur vor der ersten Tabelle).
    inst_line = f"instance = {_toml_string(key)}"
    inst_index: int | None = None
    in_table = False
    for index, line in enumerate(lines):
        if _TABLE_HEADER.match(line):
            in_table = True
            continue
        if not in_table and _INSTANCE_LINE.match(line):
            inst_index = index
            break
    if inst_index is not None:
        lines[inst_index] = inst_line
    else:
        lines.insert(0, inst_line)

    # 2) `[instances.<key>]` mit `username = "..."`.
    target = f"instances.{key}"
    user_line = f"username = {_toml_string(username)}"
    header_index: int | None = None
    for index, line in enumerate(lines):
        match = _TABLE_HEADER.match(line)
        if match and match.group(1).strip() == target:
            header_index = index
            break

    if header_index is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(f"[{target}]")
        lines.append(user_line)
    else:
        end = len(lines)
        for index in range(header_index + 1, len(lines)):
            if _TABLE_HEADER.match(lines[index]):
                end = index
                break
        for index in range(header_index + 1, end):
            if _USERNAME_LINE.match(lines[index]):
                lines[index] = user_line
                break
        else:
            lines.insert(header_index + 1, user_line)

    result = "\n".join(lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def merge_config(key: str, username: str, path: Path | None = None) -> Path:
    """Config atomar mergen (temp + rename) und den Pfad zurückgeben."""

    config_file = path or config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if config_file.is_file():
        try:
            existing = config_file.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    text = merge_config_text(existing, key, username)
    _atomic_write(config_file, text)
    return config_file


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".config-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = Path("")  # als verbraucht markieren
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
