"""Geführte Erst-Einrichtung (`ilias setup`): Instanzliste, Filter, Config-Merge.

Die CLI ist nur eine dünne Hülle: die Filterregel, die Instanz-Metadaten und
das atomare Mergen der Konfiguration leben hier.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import BUILTIN_INSTANCES

# Anzeigename und Stadt der eingebauten Instanzen (für Liste, Filter, Picker).
_DISPLAY = {
    "hhn": ("Hochschule Heilbronn", "Heilbronn"),
    "uni-mannheim": ("Universität Mannheim", "Mannheim"),
    "hs-mannheim": ("Hochschule Mannheim", "Mannheim"),
}


@dataclass(frozen=True)
class InstanceInfo:
    key: str
    name: str
    city: str
    lms: str
    auth: str
    requires_totp: bool
    base_url: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "city": self.city,
            "lms": self.lms,
            "auth": self.auth,
            "requires_totp": self.requires_totp,
            "base_url": self.base_url,
        }


def list_instances() -> list[InstanceInfo]:
    infos: list[InstanceInfo] = []
    for key, profile in BUILTIN_INSTANCES.items():
        name, city = _DISPLAY.get(key, (profile.name, ""))
        infos.append(
            InstanceInfo(
                key=key,
                name=name,
                city=city,
                lms=profile.lms,
                auth=profile.auth,
                requires_totp=profile.auth == "oidc-keycloak",
                base_url=profile.base_url,
            )
        )
    return infos


def filter_instances(text: str) -> list[InstanceInfo]:
    """Case-insensitiver Teilstring über Schlüssel, Name, Stadt und LMS."""

    needle = (text or "").strip().lower()
    if not needle:
        return list_instances()
    return [
        info
        for info in list_instances()
        if needle in info.key.lower()
        or needle in info.name.lower()
        or needle in info.city.lower()
        or needle in info.lms.lower()
    ]


# ---------------------------------------------------------------- Config-Merge

def read_stored_username(config_path: Path, instance_key: str) -> str | None:
    """Benutzername aus ``[instances.<key>]`` der Config (Default für Prompt/stdin)."""

    try:
        import tomllib

        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError):
        return None
    instances = data.get("instances")
    if not isinstance(instances, dict):
        return None
    table = instances.get(instance_key)
    if not isinstance(table, dict):
        return None
    username = table.get("username")
    return username if isinstance(username, str) and username.strip() else None


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def merge_config(text: str, instance_key: str, username: str) -> str:
    """Setzt ``instance = "<key>"`` und ``[instances.<key>] username = "…"``.

    Alle anderen Werte (base_url-Overrides, andere Instanzen, Kommentare)
    bleiben textlich erhalten.
    """

    lines = text.splitlines()
    out: list[str] = []
    in_target_table = False
    username_written = False
    instance_written = False
    seen_any_table = False

    instance_line = f'instance = "{_escape_toml_string(instance_key)}"'
    username_line = f'username = "{_escape_toml_string(username)}"'

    for line in lines:
        stripped = line.strip()
        is_table_header = stripped.startswith("[") and stripped.endswith("]")
        if is_table_header:
            if in_target_table and not username_written:
                out.append(username_line)
                username_written = True
            in_target_table = stripped == f"[instances.{instance_key}]"
            seen_any_table = True
            out.append(line)
            continue

        if not seen_any_table and re.match(r"^\s*instance\s*=", line):
            out.append(instance_line)
            instance_written = True
            continue

        if in_target_table and re.match(r"^\s*username\s*=", line):
            out.append(username_line)
            username_written = True
            continue

        out.append(line)

    if in_target_table and not username_written:
        out.append(username_line)
        username_written = True

    if not instance_written:
        # oben einfügen, vor der ersten Tabelle
        head = out[: next((i for i, line in enumerate(out) if line.strip().startswith("[")), len(out))]
        tail = out[len(head):]
        if head and head[-1].strip():
            head = [*head, ""]
        head.append(instance_line)
        if tail and tail[0].strip():
            head.append("")
        out = head + tail

    if not username_written:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[instances.{instance_key}]")
        out.append(username_line)

    return "\n".join(out) + ("\n" if out else "")


def write_config_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(prefix=".config-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmpname, path)
    finally:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
