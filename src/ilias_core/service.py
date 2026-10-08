"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .courses import apply_depth, resolve_course
from .models import (
    CourseContentsResult,
    CourseListResult,
    CourseRef,
    Credentials,
    LoginResult,
    LogoutResult,
    StatusResult,
)

if TYPE_CHECKING:  # vermeidet einen Import-Zyklus (backends -> models -> ...)
    from .backends.base import Backend


@dataclass(frozen=True)
class Service:
    instance: Instance
    backend: Backend

    @property
    def key(self) -> str:
        return self.instance.key

    def login(self, credentials: Credentials | None = None) -> LoginResult:
        """Anmelden. Ohne `credentials` wird verdeckt nach Benutzername/Passwort gefragt."""
        creds = credentials if credentials is not None else prompt_credentials()
        return self.backend.login(creds)

    def status(self) -> StatusResult:
        return self.backend.status()

    def logout(self) -> LogoutResult:
        return self.backend.logout()

    def courses(self) -> CourseListResult:
        """F2: eigene Kurse (neuestes Semester zuerst)."""
        return self.backend.courses()

    def ls(self, query: str, depth: int | None = None) -> CourseContentsResult:
        """F3: Inhalt eines Kurses als Baum.

        `query` ist eine Kurs-ID oder ein Stück aus Kurzname/Titel; die Auflösung
        (eindeutig/mehrdeutig/nicht gefunden) passiert hier im Core, nicht in der
        CLI. `depth` beschränkt die ausgegebene Tiefe (1 = nur Abschnitte).
        """
        listing = self.backend.courses()
        course = resolve_course(listing.courses, query)
        sections = apply_depth(self.backend.course_contents(course.id), depth)
        return CourseContentsResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            course=CourseRef(id=course.id, fullname=course.fullname, shortname=course.shortname),
            sections=sections,
            depth=depth,
        )


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))
