"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

from dataclasses import dataclass

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .models import Credentials, LoginResult, LogoutResult, StatusResult


@dataclass(frozen=True)
class Service:
    instance: Instance
    backend: object  # ilias_core.backends.base.Backend

    @property
    def key(self) -> str:
        return self.instance.key

    def login(self, credentials: Credentials | None = None) -> LoginResult:
        """Anmelden. Ohne `credentials` wird verdeckt nach Benutzername/Passwort gefragt."""
        creds = credentials if credentials is not None else prompt_credentials()
        return self.backend.login(creds)  # type: ignore[attr-defined]

    def status(self) -> StatusResult:
        return self.backend.status()  # type: ignore[attr-defined]

    def logout(self) -> LogoutResult:
        return self.backend.logout()  # type: ignore[attr-defined]


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))
