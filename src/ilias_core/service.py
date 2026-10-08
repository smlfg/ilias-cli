"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .errors import CoreError, ErrorResult
from .models import (
    Credentials,
    Course,
    CourseSection,
    ErrorResult as ModelErrorResult,
    LsFile,
    LsFolder,
    LsResult,
    LsUrl,
    LoginResult,
    LogoutResult,
    StatusResult,
    derive_semester,
)
from .backends.base import Backend
from .backends.moodle import resolve_course, build_ls_tree

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

    def courses(self) -> tuple[list[Course], ErrorResult | None]:
        """Eigene Kurse auflisten (Moodle nur).

        Returns (courses_list, error_result).
        Error result is None on success, otherwise contains exit code and message.
        """
        try:
            courses = self.backend.courses()
            return courses, None
        except CoreError as exc:
            return [], ErrorResult(
                command="courses",
                error_code=exc.code,
                message=exc.message,
                exit_code=exc.exit_code,
                hint=exc.hint,
                instance=self.instance.key,
                lms=self.instance.lms,
            )

    def ls(self, query: str, depth: int | None = None) -> tuple[LsResult, ErrorResult | None]:
        """Inhalt eines Kurses als Baum auflisten (Moodle nur).

        Args:
            query: Kurs-Bezeichnung (id, Teilstring von fullname/shortname) oder numerische ID
            depth: Tiefe des Baums (1=Sektionen, 2=+Module, 3=+Dateien, None=unbegrenzt)

        Returns (ls_result, error_result).
        """
        # Kurs auflisten
        try:
            courses = self.backend.courses()
        except CoreError as exc:
            return LsResult(
                instance=self.instance.key,
                lms=self.instance.lms,
                course={},
                depth=None,
                sections=[],
                timestamp="",
            ), ErrorResult(
                command="ls",
                error_code=exc.code,
                message=exc.message,
                exit_code=exc.exit_code,
                hint=exc.hint,
                instance=self.instance.key,
                lms=self.instance.lms,
            )

        # Course resolution
        resolved_course, candidates, error_code = resolve_course(query, courses)

        if error_code == "course_not_found":
            return LsResult(
                instance=self.instance.key,
                lms=self.instance.lms,
                course={},
                depth=None,
                sections=[],
                timestamp="",
            ), ErrorResult(
                command="ls",
                error_code="course_not_found",
                message=f"Kurs '{query}' nicht gefunden.",
                exit_code=1,
                instance=self.instance.key,
                lms=self.instance.lms,
            )

        if error_code == "course_ambiguous":
            candidate_list = [
                {"id": c.id, "shortname": c.shortname, "fullname": c.fullname}
                for c in candidates
            ]
            return LsResult(
                instance=self.instance.key,
                lms=self.instance.lms,
                course={},
                depth=None,
                sections=[],
                timestamp="",
            ), ErrorResult(
                command="ls",
                error_code="course_ambiguous",
                message=f"Kurs '{query}' ist mehrdeutig. Mögliche Treffer:",
                exit_code=1,
                instance=self.instance.key,
                lms=self.instance.lms,
                hint=candidate_list,
            )

        # Kurs erfolgreich aufgelöst
        if resolved_course:
            # Build the ls tree
            try:
                sections_tree = build_ls_tree(resolved_course, depth)
            except Exception:
                sections_tree = []

            # Build course dict for LsResult
            course_dict = {
                "id": resolved_course.id,
                "fullname": resolved_course.fullname,
                "shortname": resolved_course.shortname,
            }

            ls_result = LsResult(
                instance=self.instance.key,
                lms=self.instance.lms,
                course=course_dict,
                depth=depth,
                sections=sections_tree,
                timestamp="",
            )
            return ls_result, None
        else:
            # Should not happen if error_code is None, but safety first
            return LsResult(
                instance=self.instance.key,
                lms=self.instance.lms,
                course={},
                depth=None,
                sections=[],
                timestamp="",
            ), ErrorResult(
                command="ls",
                error_code="course_not_found",
                message=f"Kurs '{query}' nicht gefunden.",
                exit_code=1,
                instance=self.instance.key,
                lms=self.instance.lms,
            )


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))