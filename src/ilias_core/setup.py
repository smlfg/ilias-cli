"""Setup-Funktionalität: Instanz-Liste und Filter als Kernfunktionen (ohne CLI-Abhängigkeit)."""

from __future__ import annotations

import sys
from typing import Any

from .client import IliasClient
from .config import BUILTIN_INSTANCES, Config, InstanceProfile, load_config, save_config
from .errors import AuthenticationError, ConfigError
from .models import LoginResult


def filter_instances(text: str) -> list[InstanceProfile]:
    """Filtert die eingebauten Instanzen nach einem Suchtext (case-insensitiver Teilstring).

    Sucht in: Instanz-Schlüssel, Anzeigename, Stadt, LMS.
    """
    if not text:
        return list(BUILTIN_INSTANCES.values())

    needle = text.strip().lower()
    if not needle:
        return list(BUILTIN_INSTANCES.values())

    result = []
    for key, profile in BUILTIN_INSTANCES.items():
        haystack = " ".join([
            key,
            profile.name,
            profile.city,
            profile.lms,
        ]).lower()
        if needle in haystack:
            result.append(profile)
    return result


def instance_to_dict(profile: InstanceProfile, key: str) -> dict[str, Any]:
    """Wandelt ein InstanceProfile in ein Dict für JSON-Ausgabe um."""
    return {
        "key": key,
        "name": profile.name,
        "city": profile.city,
        "lms": profile.lms,
        "auth": profile.auth,
        "requires_totp": profile.requires_totp,
        "base_url": profile.base_url,
    }


def list_instances_json(filter_text: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Liefert die Instanz-Liste als JSON-kompatibles Dict."""
    if not filter_text:
        profiles = [(k, v) for k, v in BUILTIN_INSTANCES.items()]
    else:
        needle = filter_text.strip().lower()
        if not needle:
            profiles = [(k, v) for k, v in BUILTIN_INSTANCES.items()]
        else:
            profiles = []
            for key, profile in BUILTIN_INSTANCES.items():
                haystack = " ".join([
                    key,
                    profile.name,
                    profile.city,
                    profile.lms,
                ]).lower()
                if needle in haystack:
                    profiles.append((key, profile))
    return {"instances": [instance_to_dict(p, k) for k, p in profiles]}


def _read_stdin_lines(count: int) -> list[str]:
    """Liest bis zu `count` Zeilen von stdin (ohne TTY). Gibt Liste der Zeilen zurück (ohne Newline)."""
    lines = []
    for _ in range(count):
        line = sys.stdin.readline()
        if not line:
            break
        lines.append(line.rstrip("\n\r"))
    return lines


def _get_username_from_config(config: Config) -> str | None:
    """Liest den gespeicherten Benutzernamen für die aktuelle Instanz aus der Config."""
    config_file = config.config_dir / "config.toml"
    if not config_file.is_file():
        return None
    try:
        import tomllib
        with config_file.open("rb") as f:
            data = tomllib.load(f)
        instances = data.get("instances", {})
        inst = instances.get(config.instance)
        if inst and isinstance(inst, dict):
            return inst.get("username")
    except Exception:
        pass
    return None


def run_setup(
    instance_key: str | None,
    username: str | None,
    json_output: bool,
    is_tty: bool,
) -> LoginResult:
    """Führt den nicht-interaktiven Setup aus (Core-Logik, ohne CLI-Prompts).

    - Wenn `is_tty=False`: liest Passwort (+ bis zu 3 TOTP-Codes) zeilenweise von stdin.
    - Benötigt `instance_key` und `username` (oder Default aus Config).
    - Loggt sich über den bestehenden Auth-Adapter ein.
    - Speichert Session und aktualisiert Config atomar.
    """
    # Instanz auflösen
    if instance_key is None:
        raise ConfigError(
            "Ohne Terminal: --instance <name> angeben.",
            hint="Verfügbare Instanzen: " + ", ".join(sorted(BUILTIN_INSTANCES.keys())),
        )

    if instance_key not in BUILTIN_INSTANCES:
        raise ConfigError(f"Unbekannte Instanz {instance_key!r}.")

    # Config laden
    config = load_config(instance=instance_key)

    # Benutzername bestimmen
    if username is None:
        username = _get_username_from_config(config)
    if username is None:
        raise ConfigError(
            "Ohne Terminal: --username <name> angeben oder Benutzername in Config gespeichert haben.",
            hint=f"ilias setup --instance {instance_key} --username <name> ...",
        )

    # Passwort und TOTP lesen
    if not is_tty:
        lines = _read_stdin_lines(4)  # password + up to 3 TOTP codes
        if not lines:
            raise AuthenticationError("Abgebrochen, nichts gespeichert.")
        password = lines[0]
        totp_codes = lines[1:] if len(lines) > 1 else []
    else:
        # Interactive path will be handled by CLI (S4)
        raise ConfigError("Interaktiver Modus noch nicht implementiert (S4).")

    # Login durchführen
    client = IliasClient(config)

    # TOTP-Callback erstellen, der die Codes nacheinander verbraucht
    totp_index = 0
    requires_totp = BUILTIN_INSTANCES[instance_key].requires_totp

    def otp_callback() -> str:
        nonlocal totp_index
        if totp_index < len(totp_codes):
            code = totp_codes[totp_index]
            totp_index += 1
            return code
        return ""

    try:
        result = client.login(username, password, otp_callback if requires_totp else None)
    except AuthenticationError:
        # Re-raise with proper message
        raise

    # Config atomar aktualisieren
    save_config(config.config_dir, instance_key, username)

    return result