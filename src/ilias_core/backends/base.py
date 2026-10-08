"""Backend-Schnittstelle: Auth/Session/Operationen pro LMS/ILIAS (ANFORDERUNGEN.md §1)."""

from __future__ import annotations

import abc
from collections.abc import Callable
from typing import Any

from ..config import Instance
from ..models import Course, Credentials, LogoutResult, Section


class Backend(abc.ABC):
    """Ein Backend kapselt Login, Status, Logout, Kurse und Kursinhalt einer Instanz."""

    name: str = "abstract"
    supports_login: bool = False
    #: False, wenn courses/ls (F2/F3) für dieses LMS nicht implementiert sind
    supports_courses: bool = True
    uses_totp: bool = False

    def __init__(self, instance: Instance) -> None:
        self.instance = instance

    @property
    def key(self) -> str:
        return self.instance.key

    @property
    def base_url(self) -> str:
        return self.instance.normalized_base_url

    @abc.abstractmethod
    def login(
        self, credentials: Credentials, otp_callback: Callable[[], str] | None = None
    ) -> Any:
        """Anmelden, Ergebnis prüfen und erst dann die Session speichern.

        Rückgabe: ``LoginResult`` (ILIAS) bzw. ``MoodleLoginResult`` (Moodle).
        """

    @abc.abstractmethod
    def status(self) -> Any:
        """Gespeicherte Session gegen den Server prüfen."""

    @abc.abstractmethod
    def logout(self) -> LogoutResult:
        """Lokale Session löschen."""

    @abc.abstractmethod
    def courses(self) -> list[Course]:
        """Kurse des angemeldeten Nutzers (F2)."""

    @abc.abstractmethod
    def course_contents(self, course_id: int) -> list[Section]:
        """Inhalt eines Kurses als Abschnitts-/Modul-Baum (F3)."""
