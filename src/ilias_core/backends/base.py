"""Backend-Schnittstelle. Ein Backend kapselt das LMS-spezifische Login/HTTP."""

from __future__ import annotations

from typing import Protocol

from ..models import SiteInfo


class Backend(Protocol):
    def get_token(self, username: str, password: str) -> str:
        """Authentifizieren und einen Token liefern (noch nicht gespeichert)."""

    def get_site_info(self, token: str) -> SiteInfo:
        """Token verifizieren und Sitzungsinformationen liefern."""

    def close(self) -> None:
        """Ressourcen freigeben."""
