"""ILIAS-Setup: geführte Erst-Einrichtung und Instanz-Filterung.

Stellt die Kernfunktion `filter_instances` bereit und die Konfiguration
aller eingebauten Instanzen (hhn, uni-mannheim, hs-mannheim).
"""

from __future__ import annotations

import re
from typing import Any

from .config import BUILTIN_INSTANCES, InstanceProfile, load_config


def _requires_totp(profile: InstanceProfile) -> bool:
    """True nur für hhn (OIDC/Keycloak + TOTP)."""
    return profile.auth == "oidc-keycloak"


def _instance_dict(key: str, profile: InstanceProfile) -> dict[str, Any]:
    """Erstelle einen Instanz-Dict für die JSON-Antwort."""
    return {
        "key": key,
        "name": profile.name,
        "lms": profile.lms,
        "auth": profile.auth,
        "requires_totp": _requires_totp(profile),
        "base_url": profile.base_url,
    }


def filter_instances(text: str) -> dict[str, Any]:
    """Filter builtin instances by case-insensitive substring over key, name, city, LMS.

    Returns the full instance dict matching the filter text.
    Wenn text leer ist, werden alle Instanzen zurückgegeben.
    """
    if not text or not text.strip():
        return {"instances": [_instance_dict(key, profile) for key, profile in BUILTIN_INSTANCES.items()]}

    text_lower = text.strip().lower()
    result: dict[str, Any] = {"instances": []}

    for key, profile in BUILTIN_INSTANCES.items():
        # case-insensitive substring über key, name, city, LMS
        if (text_lower in key.lower()
                or text_lower in profile.name.lower()
                or text_lower in profile.city.lower()
                or text_lower in profile.lms.lower()):
            result["instances"].append(_instance_dict(key, profile))

    return result


def list_instances(text: str | None = None) -> dict[str, Any]:
    """Öffne die Instanz-Liste (für CLI `--list [--filter TEXT]`)."""

    if text and text.strip():
        return filter_instances(text.strip())
    return {"instances": [_instance_dict(key, profile) for key, profile in BUILTIN_INSTANCES.items()]}


def load_instance_config(key: str | None = None) -> dict[str, Any]:
    """Lade die Konfiguration für eine Instanz (für `--instance NAME`)."""

    config = load_config(instance=key)
    return {
        "instance": config.instance,
        "base_url": config.base_url,
        "client_id": config.client_id,
        "auth": config.auth,
        "lms": config.lms,
    }