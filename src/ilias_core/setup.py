"""Setup-Funktionalität: Instanz-Liste und Filter als Kernfunktionen (ohne CLI-Abhängigkeit)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import BUILTIN_INSTANCES, InstanceProfile


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