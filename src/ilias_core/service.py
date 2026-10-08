"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .courseview import apply_depth, build_sections
from .errors import CourseAmbiguousError, CourseNotFoundError
from .models import (
    Course,
    CoursesResult,
    Credentials,
    LoginResult,
    LogoutResult,
    LsResult,
    StatusResult,
    semester_rank,
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

    def courses(self) -> CoursesResult:
        courses = sorted(
            self.backend.courses(),
            key=lambda c: (
                # neuestes Semester zuerst, None zuletzt, dann fullname
                -_semester_sort(c.semester),
                c.fullname.lower(),
            ),
        )
        return CoursesResult(instance=self.instance.key, lms=self.instance.lms, courses=tuple(courses))

    def ls(self, query: str, depth: int | None = None) -> LsResult:
        courses = self.backend.courses()
        course = resolve_course(courses, query)
        raw = self.backend.course_contents(course.id)
        sections = apply_depth(build_sections(raw), depth)
        return LsResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            course={"id": course.id, "fullname": course.fullname, "shortname": course.shortname},
            depth=depth,
            sections=tuple(sections),
            )


def _semester_sort(semester: str | None) -> int:
    rank = semester_rank(semester)
    return rank[0] * 10 + rank[1]


def resolve_course(courses: list[Course], query: str) -> Course:
    """Kurs auflösen: id, dann exakter Kurz-/Langname, dann Teilstring."""
    query = query.strip()
    if query.isdigit():
        by_id = [c for c in courses if c.id == int(query)]
        if len(by_id) == 1:
            return by_id[0]
        raise CourseNotFoundError(
            f"Kein Kurs mit der id {query} in dieser Instanz.",
            hint="`ilias courses` listet die eigenen Kurse.",
        )
    lowered = query.lower()
    exact = [
        c for c in courses if c.shortname.lower() == lowered or c.fullname.lower() == lowered
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise CourseAmbiguousError(
            _ambiguous_message(query, exact),
            candidates=[c.candidate() for c in exact],
        )
    matches = [
        c for c in courses if lowered in c.shortname.lower() or lowered in c.fullname.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CourseNotFoundError(
            f"Kein Kurs gefunden für {query!r}.",
            hint="`ilias courses` listet die eigenen Kurse.",
        )
    raise CourseAmbiguousError(
        _ambiguous_message(query, matches),
        candidates=[c.candidate() for c in matches],
    )


def _ambiguous_message(query: str, matches: list[Course]) -> str:
    lines = [f"Mehrere Kurse passen zu {query!r}:"]
    for c in matches:
        lines.append(f"  [{c.id}] {c.shortname} – {c.fullname}")
    lines.append("Bitte genauer angeben (id oder eindeutiger Name).")
    return "\n".join(lines)


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))
