"""Strukturierte Datenmodelle der ILIAS-CLI.

Die Modelle enthalten bewusst **keine** Cookies, Passwörter oder Secrets.
Sie sind die einzige Oberfläche, die an CLI oder MCP weitergegeben wird.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LoginResult:
    """Ergebnis eines erfolgreichen, verifizierten Logins."""

    authenticated: bool
    base_url: str
    client_id: str
    method: str = "oidc-keycloak"
    message: str = ""
    instance: str = "hhn"
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionStatus:
    """Ergebnis einer Session-Gültigkeitsprüfung."""

    authenticated: bool
    base_url: str
    client_id: str
    message: str = ""
    instance: str = "hhn"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
