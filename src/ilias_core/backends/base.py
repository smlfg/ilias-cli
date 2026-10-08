"""Backend-Schnittstelle: Auth/Session/Operationen pro LMS/ILIAS (ANFORDERUNGEN.md §1)."""

from __future__ import annotations

import abc

from ..config import Instance
from ..models import (
    Credentials,
    Course,
    CourseSection,
    ErrorResult,
    LoginResult,
    LogoutResult,
    StatusResult,
)


class Backend(abc.ABC):
    """Ein Backend kapselt Login, Status und Logout einer Instanz."""

    name: str = "abstract"
    supports_login: bool = False

    def __init__(self, instance: Instance) -> None:
        self.instance = instance

    @property
    def key(self) -> str:
        return self.instance.key

    @property
    def base_url(self) -> str:
        return self.instance.normalized_base_url

    @abc.abstractmethod
    def login(self, credentials: Credentials) -> LoginResult:
        """Anmelden, Ergebnis prüfen und erst dann die Session speichern."""

    @abc.abstractmethod
    def status(self) -> StatusResult:
        """Gespeicherte Session gegen den Server prüfen."""

    @abc.abstractmethod
    def logout(self) -> LogoutResult:
        """Lokale Session löschen."""

    @abc.abstractmethod
    def courses(self) -> list[Course]:
        """Eigene Kurse auflisten (Moodle nur)."""

    @abc.abstractmethod
    def course_contents(self, course_id: int) -> list[CourseSection]:
        """Inhalt eines Kurses als Abschnitt-Liste holen (Moodle nur)."""
