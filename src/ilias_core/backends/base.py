"""Backend-Schnittstelle: Auth/Session/Operationen pro LMS/ILIAS (ANFORDERUNGEN.md §1)."""

from __future__ import annotations

import abc

from ..config import Instance
from ..models import (
    Course,
    CourseListResult,
    Credentials,
    LoginResult,
    LogoutResult,
    SectionNode,
    StatusResult,
)


class Backend(abc.ABC):
    """Ein Backend kapselt Login, Status, Logout und die Lese-Operationen."""

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
    def courses(self) -> CourseListResult:
        """Eigene Kurse des angemeldeten Benutzers (F2)."""

    @abc.abstractmethod
    def course_contents(self, course_id: int) -> tuple[SectionNode, ...]:
        """Abschnitte und Module eines Kurses als Baum (F3).

        Nur die Rohdaten: Auflösung der Kursangabe und `--depth` passieren in
        `ilias_core.service.Service.ls`.
        """
